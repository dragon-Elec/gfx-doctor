#!/usr/bin/env python3
#
# gfx-doctor.py - v1.0
# A robust diagnostic and restoration tool for the Mesa graphics stack on
# Debian/Ubuntu-based systems, written in Python for maximum reliability.
#
# This tool fixes the flaws of prior shell-based versions by:
# 1. Using the `python3-apt` API for direct, error-proof package analysis.
# 2. Implementing a correct, multi-stage repair process (pin, update, dist-upgrade, autoremove).
# 3. Performing comprehensive and accurate system diagnostics.
#

import sys
import os
import subprocess
import shutil
import atexit
import argparse
import urllib.request
import urllib.error
import socket
from typing import List, Set

def _preflight_error(text: str):
    """A minimal error printer for use before the main UI is set up."""
    red = ''
    reset = ''
    # Check stderr for color support, as that's where we are printing.
    if sys.stderr.isatty():
        red = '\033[31m'
        reset = '\033[0m'
    print(f"{red}✖{reset} {text}", file=sys.stderr)
    sys.exit(1)

try:
    import apt
except ImportError:
    _preflight_error("The 'python3-apt' library is required. Please install it with 'sudo apt-get install python3-apt'.")


# --- Global Constants ---
SCRIPT_VERSION = "1.0"
OVERRIDE_FILE = "/etc/apt/preferences.d/99-gfx-doctor-override.pref"
MIN_FREE_SPACE_MB = 500
OFFICIAL_SITES = ["archive.ubuntu.com", "security.ubuntu.com", "packages.zorin.com"]
PPA_KEYWORDS = ["kisak", "oibaf", "padoka"]

# --- ANSI Color Class for UI ---
class Colors:
    if sys.stdout.isatty():
        RESET = '\033[0m'
        RED = '\033[31m'
        GREEN = '\033[32m'
        YELLOW = '\033[33m'
        BLUE = '\033[34m'
        BOLD = '\033[1m'
    else:
        RESET = RED = GREEN = YELLOW = BLUE = BOLD = ''

# --- UI & Helper Functions ---
def msg_info(text: str): print(f"{Colors.BLUE}==>{Colors.RESET}{Colors.BOLD} {text}{Colors.RESET}")
def msg_ok(text: str): print(f"{Colors.GREEN} ✔ {Colors.RESET} {text}")
def msg_warn(text: str): print(f"{Colors.YELLOW} ! {Colors.RESET} {text}")
def msg_error(text: str):
    print(f"{Colors.RED} ✖ {Colors.RESET} {text}", file=sys.stderr)
    sys.exit(1)

# --- The Main Class ---
class GfxDoctor:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.os_codename = ""
        self.foreign_origins: Set[str] = set()
        self.held_packages: List[str] = []
        self.dpkg_remnants: List[str] = []
        self.graphics_packages: List[str] = []
        self.apt_cache = None

    def _cleanup(self):
        """Registered with atexit to ALWAYS run on script exit."""
        if os.path.exists(OVERRIDE_FILE):
            print() # Newline for cleaner exit
            msg_warn("Cleanup: Removing temporary override file...")
            if not self.dry_run:
                subprocess.run(['sudo', 'rm', '-f', OVERRIDE_FILE], check=True)
            msg_ok("Cleanup complete.")

    def run_command(self, cmd: List[str], check: bool = True, capture: bool = False):
        """Helper to run system commands."""
        kwargs = {'check': check, 'text': True}
        if capture:
            kwargs['capture_output'] = True
        
        result = subprocess.run(cmd, **kwargs)
        return result.stdout.strip() if capture else None

    def perform_preflight_checks(self):
        msg_info("Performing pre-flight system checks...")
        if os.geteuid() != 0:
            msg_error("This script must be run with sudo or as root.")

        try:
            self.os_codename = self.run_command(['lsb_release', '-cs'], capture=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            msg_error("Could not determine OS codename via 'lsb_release'.")

        try:
            result = subprocess.run(['dpkg', '--audit'], capture_output=True, text=True)
            if result.stdout:
                msg_error("Broken packages detected. Please run 'sudo dpkg --configure -a' first.")
        except FileNotFoundError:
            msg_error("'dpkg' command not found. This is not a Debian-based system.")

        free_space_gb = shutil.disk_usage('/var/cache/apt').free / (1024**3)
        if free_space_gb * 1024 < MIN_FREE_SPACE_MB:
            msg_error(f"Insufficient disk space in /var. Need at least {MIN_FREE_SPACE_MB}MB.")

        try:
            # More reliable check than ping, as ICMP can be blocked.
            # Use a HEAD request for efficiency.
            req = urllib.request.Request('http://packages.ubuntu.com', method='HEAD')
            urllib.request.urlopen(req, timeout=10)
        except (urllib.error.URLError, socket.timeout):
            msg_error("No network connectivity detected. Internet is required.")
        
        msg_ok(f"System health checks passed. Detected OS codename: '{self.os_codename}'")

    def _detect_llvm_package(self) -> str:
        """Dynamically and robustly detects the correct LLVM package."""
        llvm_candidates: Set[str] = set()
        # Triangulate from two core packages for robustness
        for pkg_name in ['libgl1-mesa-dri', 'mesa-vulkan-drivers']:
            try:
                pkg = self.apt_cache[pkg_name]
                if pkg.is_installed:
                    for dep_list in pkg.installed.dependencies:
                        for dep in dep_list:
                            if dep.name.startswith('libllvm'):
                                llvm_candidates.add(dep.name)
            except KeyError:
                continue # Package might not exist on a broken system

        if len(llvm_candidates) == 1:
            llvm_pkg = llvm_candidates.pop()
            msg_ok(f"Dynamically detected LLVM package: {llvm_pkg}")
            return llvm_pkg
        elif len(llvm_candidates) > 1:
            msg_warn("Conflicting LLVM dependencies found. The system state is inconsistent.")
            return ""
        else:
            msg_warn("Could not dynamically detect LLVM package.")
            return ""

    def discover_package_list(self):
        msg_info("Discovering graphics stack package list...")
        self.apt_cache = apt.Cache()
        
        base_packages = [
            'libgl1-mesa-dri', 'libglx-mesa0', 'libgbm1', 'libegl-mesa0',
            'mesa-vulkan-drivers', 'mesa-va-drivers', 'mesa-vdpau-drivers',
            'libxatracker2', 'libglapi-mesa', 'libdrm2', 'libdrm-amdgpu1',
            'libdrm-intel1', 'libdrm-nouveau2', 'libdrm-radeon1'
        ]
        
        llvm_pkg = self._detect_llvm_package()
        if llvm_pkg:
            base_packages.append(llvm_pkg)

        # Filter list to only include packages that actually exist in the cache
        self.graphics_packages = [p for p in base_packages if p in self.apt_cache]
        msg_ok(f"Package discovery complete ({len(self.graphics_packages)} packages).")

    def _get_package_status(self, pkg_name: str) -> str:
        """Uses the python3-apt API to get the true origin of a package."""
        try:
            pkg = self.apt_cache[pkg_name]
            if not pkg.is_installed:
                return f"{Colors.YELLOW}[MISSING]{Colors.RESET}"
            
            origin = pkg.installed.origins[0]
            # Check if origin is from the current OS release or a known official site
            if origin.archive.startswith(self.os_codename) or any(site in origin.site for site in OFFICIAL_SITES):
                return f"{Colors.GREEN}[STOCK]{Colors.RESET}"
            else:
                self.foreign_origins.add(origin.label)
                return f"{Colors.RED}[FOREIGN]{Colors.RESET} (from {origin.site})"
        except KeyError:
            return f"{Colors.YELLOW}[NOT FOUND]{Colors.RESET}"

    def run_diagnosis(self):
        msg_info("Running diagnosis...")
        self.apt_cache = apt.Cache()  # FIX: Re-open cache to avoid stale data
        self.foreign_origins.clear()  # Clear previous results for re-runs

        # Analyze all packages first to collect their statuses and origins
        package_statuses = {pkg: self._get_package_status(pkg) for pkg in self.graphics_packages}

        # Detect 'rc' state packages
        self.dpkg_remnants = []
        dpkg_output = self.run_command(['dpkg-query', '-W', '-f=${db:Status-Abbrev}\t${Package}\n'], capture=True)
        for line in dpkg_output.splitlines():
            if line.startswith('rc'):
                self.dpkg_remnants.append(line.split('\t')[1])

        print("\n--- Gfx-Doctor Diagnostic Report ---")
        if self.foreign_origins:
            msg_warn("Detected packages from foreign repositories:")
            # Using sorted(list(...)) to ensure consistent output order
            for origin in sorted(list(self.foreign_origins)):
                print(f"  - {origin}")
        else:
            msg_ok("No packages from foreign graphics PPAs detected.")

        if self.dpkg_remnants:
            msg_warn("Detected package remnants (removed but not purged):")
            for pkg in self.dpkg_remnants:
                print(f"  - {pkg}")

        print()  # Add a blank line for spacing
        msg_info("Analyzing core package status:")
        for pkg, status in package_statuses.items():
            print(f"  {pkg:<25} {status}")
        print("------------------------------------")

    def perform_force_downgrade(self):
        msg_info("Preparing to force downgrade graphics stack to stock...")
        if not self.dry_run:
            if not input(f"{Colors.YELLOW}{Colors.BOLD}This will modify your system. Type 'yes' to continue: {Colors.RESET}").lower() == 'yes':
                msg_warn("Operation cancelled.")
                return False

        if os.path.exists(OVERRIDE_FILE):
            msg_error(f"Stale override file found at {OVERRIDE_FILE}. Please remove it manually.")

        if self.dry_run:
            msg_info(f"DRY-RUN: Would create override file pinning {len(self.graphics_packages)} graphics packages to release '{self.os_codename}'.")
            msg_info("DRY-RUN: Would run 'apt-get update'.")
            msg_info("DRY-RUN: Would run 'apt-get dist-upgrade'.")
            msg_info("DRY-RUN: Would run 'apt-get autoremove'.")
            if self.dpkg_remnants:
                msg_info(f"DRY-RUN: Would purge {len(self.dpkg_remnants)} package remnants.")
            return True

        try:
            # ENHANCEMENT: Pin only the graphics packages to avoid unintended system-wide downgrades.
            msg_info(f"Step 1: Creating temporary apt override file for {len(self.graphics_packages)} graphics packages...")
            packages_to_pin = " ".join(self.graphics_packages)
            pin_content = f"""
# Managed by gfx-doctor.py - will be removed automatically.
Package: {packages_to_pin}
Pin: release n={self.os_codename}
Pin-Priority: 1001
"""
            # Use subprocess to write the file with sudo
            subprocess.run(['sudo', 'tee', OVERRIDE_FILE], input=pin_content, text=True, check=True, stdout=subprocess.DEVNULL)
            
            msg_info("Step 2: Updating package lists with new priorities...")
            self.run_command(['sudo', 'apt-get', 'update'])

            # Flaw #5 Fix: Use dist-upgrade for complete cleanup
            msg_info("Step 3: Forcing downgrade and dependency reconciliation...")
            self.run_command(['sudo', 'apt-get', 'dist-upgrade', '-y'])
            
            msg_info("Step 4: Removing any orphaned packages...")
            self.run_command(['sudo', 'apt-get', 'autoremove', '-y'])

            msg_info("Step 5: Purging any orphaned package configuration files...")
            if self.dpkg_remnants:
                self.run_command(['sudo', 'apt-get', 'purge', '-y'] + self.dpkg_remnants)
                msg_ok(f"Purged {len(self.dpkg_remnants)} package remnants.")
            else:
                msg_ok("No package remnants found to purge.")

        except subprocess.CalledProcessError as e:
            msg_error(f"A command failed during the repair process: {e}")
            return False
        
        # The atexit trap will handle cleanup automatically from here.
        msg_ok("System restoration process complete.")
        return True

    def run(self, args):
        self.dry_run = args.dry_run
        atexit.register(self._cleanup)
        
        self.perform_preflight_checks()
        self.discover_package_list()

        while True:
            self.run_diagnosis()
            print("Please choose an action:")
            print("  [S] Force Downgrade ALL graphics packages to Stock (Recommended Fix)")
            print("  [V] Verify Graphics Stack (Re-run diagnosis)")
            print("  [Q] Quit")
            choice = input("Enter your choice: ").lower()

            if choice == 's':
                if self.perform_force_downgrade():
                    msg_ok("Action completed successfully.")
                    if not self.dry_run:
                        print("\n--- Post-Action Verification ---")
                        self.run_diagnosis()
                        msg_warn("A system reboot is required for all changes to take effect.")
                        if input("Reboot now? [y/N] ").lower() == 'y':
                            self.run_command(['sudo', 'reboot'])
                    break
            elif choice == 'v':
                continue
            elif choice == 'q':
                break
            else:
                msg_warn("Invalid option.")

        msg_info("Exiting gfx-doctor.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A robust diagnostic and restoration tool for the Mesa graphics stack.")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Simulate actions without modifying the system.")
    args = parser.parse_args()
    
    doctor = GfxDoctor(dry_run=args.dry_run)
    doctor.run(args)
