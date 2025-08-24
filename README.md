# gfx-doctor.py

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

A robust diagnostic and restoration tool for the Mesa graphics stack on Debian/Ubuntu-based systems. This script is designed to safely and effectively revert a system's graphics drivers to the official, stock versions provided by the OS repositories.

---

### ⚠️ Development Status & Disclaimer

**This script is currently in a development stage and should be considered experimental.**

While it has been designed with robust safety features, it has **not been rigorously tested** across a wide variety of hardware, software configurations, or distribution versions.

Running this script can make significant changes to your system's core graphics packages. There is a possibility of unintended consequences, including a non-booting system. **Always back up important data before running this tool.**

**Use at your own risk.** The authors and contributors are not liable for any damage that may occur.

---

### Why Does This Tool Exist?

On Debian-based systems, third-party graphics PPAs (like Kisak-Mesa or Oibaf) provide bleeding-edge drivers, which are great for gaming but can sometimes cause instability or break professional applications.

Unfortunately, removing these PPAs can be difficult. The standard `ppa-purge` tool can fail if dependencies are complex, leaving the system in a broken state with "stuck" or missing packages. This tool was created to solve that problem decisively.

### Features

*   **Comprehensive Diagnosis:** Scans your system for foreign repositories, leftover package configurations (`rc` state), and analyzes the origin of every core graphics package.
*   **Safe Restoration:** Uses `apt` pinning to surgically and forcefully downgrade all graphics packages to the official OS versions, succeeding where `ppa-purge` might fail.
*   **Dynamic & Future-Proof:** Automatically detects the correct `libllvm` version and other dependencies for your specific OS release (e.g., `jammy`, `noble`), so it won't become outdated.
*   **Robust Safety Checks:** Performs pre-flight checks for root access, disk space, broken packages, and network connectivity before attempting any changes.
*   **No Trace Left Behind:** Guarantees cleanup of all its temporary files, even if the script is interrupted or fails.

### Requirements

*   A Debian-based OS (e.g., Ubuntu 22.04+, Zorin OS 17+, Linux Mint 21+).
*   Python 3.
*   The `python3-apt` library.
*   `sudo` / root privileges.

### Installation

1.  **Install the required dependency:**
    ```bash
    sudo apt update
    sudo apt install python3-apt
    ```

2.  **Clone this repository:**
    ```bash
    git clone [URL_OF_YOUR_GIT_REPOSITORY]
    cd gfx-doctor
    ```

### Usage

It is **highly recommended** to run the script with the `--dry-run` flag first. This will simulate all actions without making any changes to your system.

1.  **Run a Dry Run Simulation:**
    ```bash
    sudo python3 gfx-doctor.py --dry-run
    ```
    Review the output carefully to understand what the script intends to do.

2.  **Execute the Fix:**
    If you are satisfied with the dry run, run the script without the flag to apply the changes.
    ```bash
    sudo python3 gfx-doctor.py
    ```
    The script is interactive and will ask for final confirmation before modifying your system. A reboot is required after the process is complete.

### License

This project is licensed under the MIT License - see the `LICENSE` file for details.
