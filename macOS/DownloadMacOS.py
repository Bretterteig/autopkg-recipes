#!/usr/bin/env python
# This processor uses the softwareupdate binary to query for new macOS builds, downloads them and provides the path to the app.
#
# ATTENTION: This processor has requirements:
#   * macOS Big Sur or higher (tested on Big Sur)

from __future__ import absolute_import

import os, subprocess, json, plistlib
from distutils.version import LooseVersion

from autopkglib import Processor, ProcessorError

__all__ = ["DownloadMacOS"]

class DownloadMacOS(Processor):
    description = __doc__

    input_variables = {}

    output_variables = {
        "version": {"description": "Version of the macOS Installer"},
        "pathname": {"description": "Location of the installer"},
        "release": {"description": "The name of the current OS"},
        "size": {"description": "The size of the installer"},
        "changed": {"description": "Describes wether or not a new version has been downloaded"}
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
        output = subprocess.check_output(['/usr/bin/hdiutil', 'detach', path, '-force'])
        return output


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


    # Software update functions
    def get_update(self):
        # Use softwareupdates list function to get all currently offered builds
        try:
            result = subprocess.run(['/usr/sbin/softwareupdate', '--list-full-installers'], stdout=subprocess.PIPE)
        except Exception as err:
            raise ProcessorError(err)

        # Parse the text into a list of dicts
        update_list = []
        for line in result.stdout.decode().split('\n'):
            if "Version" in line:
                update_info = [s.split(':')[1].strip() for s in line.split(',')]
                update_list.append({
                    "name": update_info[0],
                    "version": update_info[1],
                    "size": (int(update_info[2].rstrip('K')) * 1000)
                })

        # Check if the list creation was successful
        if not update_list:
            raise ProcessorError("No updates have been found")

        # Sort this list by the version key. Highest beeing the first item
        update_list = sorted(update_list, key=lambda k: k['version'], reverse=True)
        # Make the update known
        update = update_list[0]

        if self.env['verbose'] >= 2:
            self.output("The following updates have been found: " + json.dumps(update_list, indent = 4))
        self.output("Latest version found is {} {}".format(update['name'], update['version']))

        return update

    def download_macos(self, update):
        # Run download process
        try:
            subprocess.run( ['/usr/sbin/softwareupdate', '--fetch-full-installer', '--full-installer-version', update['version']] )
        except Exception as err:
            raise ProcessorError(err)

        # Check if we actually successfully downloaded something
        installer = self.get_local_installer('/Applications', update['version'])
        if not installer:
            raise ProcessorError("Download was not successful or cannot find downloaded item")

        return installer


    # Main
    def main(self):
        # Get the list of installers from the softwareupdate binary
        self.output("Querying software update for macOS installers")
        update = self.get_update()

        # Check if application is already downloaded
        self.output('Checking "/Applications" for the correct installer')
        self.env["changed"] = False
        installer = self.get_local_installer('/Applications', update['version'])
        if not installer:
            self.env["changed"] = True
            self.output("Downloading macOS {} {} (Size: {})".format(update['name'], update['version'], update['size']))
            installer = self.download_macos(update)
        else:
            self.output("Version already on system at {}".format(installer))


        # Set env variables
        self.env["pathname"] = installer
        self.env["version"] = update['version']
        self.env["release"] = update['name']
        self.env["size"] = update['size']


if __name__ == "__main__":
    PROCESSOR = DownloadMacOS()
    PROCESSOR.execute_shell()