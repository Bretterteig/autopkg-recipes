#!/usr/bin/env python
# This processor uses the softwareupdate to download the macOS version determined by macOSReleaseProvider.
# Some functions heavily burrow from munkitools code
#
# ATTENTION: This processor has requirements:
#   * macOS Big Sur or higher (tested on Big Sur)

from __future__ import absolute_import

import os, subprocess, json, plistlib, shutil
from distutils.version import LooseVersion

from autopkglib import Processor, ProcessorError

__all__ = ["macOSDownloader"]

class macOSDownloader(Processor):
    description = __doc__

    input_variables = {
        "version": {
            "description": "Variables are provided by macOSReleaseProvider processor",
            "required": True
        },
        "release": {
            "description": "Variables are provided by macOSReleaseProvider processor",
            "required": True
        },
        "size": {
            "description": "Variables are provided by macOSReleaseProvider processor",
            "required": True
        },
    }

    output_variables = {
        "pathname": {"description": "Location of the installer"},
        "cache_dir": {"description": "The directory the installer is located in. Good for use with DMGCreator"},
        "changed": {"description": "Describes wether or not a new version has been downloaded"},
        "macOSDownloader_summary_result": {"description": "Outputs the result of the download process"},
    }


    # DMG HELER FUNCTIONS
    def get_dmg_mount_point(self, path):
        current_mounts = plistlib.loads(subprocess.check_output(['/usr/bin/hdiutil', 'info', '-plist']))['images']
        for mount in current_mounts:
            if mount['image-path'] == path:
                for info in mount['system-entities']:
                    if 'mount-point' in info:
                        return info['mount-point']
        return None

    def mount_dmg(self, path):
        mount_point = self.get_dmg_mount_point(path)
        if mount_point:
            return mount_point
  
        try:
            output = plistlib.loads(subprocess.check_output(['/usr/bin/hdiutil', 'attach', path, '-nobrowse', '-plist']))
        except:
            raise ProcessorError("Could not mount {}".format(path))

        output = [d for d in output['system-entities'] if 'mount-point' in d][0]
        return output['mount-point']

    def unmount_dmg(self, path):
        return subprocess.check_output(['/usr/bin/hdiutil', 'detach', path, '-force'])


    # Installer app functions
    def get_local_installer(self, dir, version):
        for item in os.listdir(dir):
            item_path = os.path.join(dir, item)
            startosinstall_path = os.path.join(item_path, 'Contents/Resources/startosinstall')
            if os.path.exists(startosinstall_path):
                local_version = self.get_os_version(item_path)
                if LooseVersion(local_version) == LooseVersion(version):
                    return item_path
        return None

    def get_os_version(self, app_path):
        installinfo_plist = os.path.join(app_path, 'Contents/SharedSupport/InstallInfo.plist')
        if os.path.isfile(installinfo_plist):
            return self.get_plist_key(installinfo_plist, 'System Image Info:version')

        sharedsupport_dmg = os.path.join(app_path, 'Contents/SharedSupport/SharedSupport.dmg')
        if os.path.isfile(sharedsupport_dmg):
            mountpoint = self.mount_dmg(sharedsupport_dmg)
            if mountpoint:
                info_plist_path = os.path.join(mountpoint, "com_apple_MobileAsset_MacSoftwareUpdate", "com_apple_MobileAsset_MacSoftwareUpdate.xml")
                try:
                    info = plistlib.readPlist(info_plist_path)
                    return info['Assets'][0]['OSVersion']
                except:
                    return ''
                finally:
                    self.unmount_dmg(mountpoint)
        return ''

    # Softwareupdate functions
    def download_macos(self):
        # Run download process
        try:
            subprocess.run( ['/usr/sbin/softwareupdate', '--fetch-full-installer', '--full-installer-version', self.env['version']] )
        except Exception as err:
            raise ProcessorError(err)

        # Check if we actually successfully downloaded something
        installer = self.get_local_installer('/Applications', self.env['version'])
        if not installer:
            raise ProcessorError("Download was not successful or cannot find downloaded item")

        return installer


    # Main
    def main(self):
        # Define variables
        cache_path = os.path.join(self.env['RECIPE_CACHE_DIR'], "downloads", self.env['version'])
        installer_cache_path = os.path.join(cache_path, "Install {}.app".format(self.env['release']))
        self.env["cache_dir"] = cache_path
        self.env["pathname"] = installer_cache_path

        # Check if dmg already in cache
        self.env["changed"] = False
        if os.path.exists(installer_cache_path):
            self.output("Using chached version at {}".format(installer_cache_path))
            return  

        # Check if application is already downloaded
        self.output('No cached installer found. Checking "/Applications" for the correct installer')
        self.env["changed"] = True
        installer = self.get_local_installer('/Applications', self.env['version'])
        if not installer:
            self.output("Downloading macOS {} {} (Size: {})".format(self.env['release'], self.env['version'], self.env['size']))
            installer = self.download_macos()
            self.env['macOSDownloader_summary_result'] = {
                "summary_text": "New version of macOS has been downloaded",
                "data": {
                    "release": self.env["release"],
                    "version": self.env["version"],
                    "download_path": self.env["pathname"]
                }
            }
        else:
            self.output("Version already on system at {}".format(installer))

        # Copy installer into cache
        self.output("Creating copy for cache")
        os.makedirs(os.path.join(cache_path), exist_ok=True)
        shutil.copytree(installer, installer_cache_path)



if __name__ == "__main__":
    PROCESSOR = macOSDownloader()
    PROCESSOR.execute_shell()