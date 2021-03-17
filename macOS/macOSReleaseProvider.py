#!/usr/bin/env python
# This processor uses the softwareupdate binary to query for new macOS builds.
#
# ATTENTION: This processor has requirements:
#   * macOS Big Sur or higher (tested on Big Sur)

from __future__ import absolute_import

import os, subprocess, json, plistlib, shutil
from distutils.version import LooseVersion

from autopkglib import Processor, ProcessorError

__all__ = ["macOSReleaseProvider"]

class macOSReleaseProvider(Processor):
    description = __doc__

    input_variables = {}

    output_variables = {
        "version": {"description": "Version of the macOS Installer"},
        "release": {"description": "The name of the current OS"},
        "size": {"description": "The size of the installer"},
    }



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
                    "size": update_info[2]
                })

        # Check if the list creation was successful
        if not update_list:
            raise ProcessorError("Could not receive or parse updates")

        # Sort this list by the version key. Highest beeing the first item
        update_list = sorted(update_list, key=lambda k: k['version'], reverse=True)
        # Select the one with the hightes version number
        update = update_list[0]

        if self.env['verbose'] >= 3:
            self.output("The following updates have been found: " + json.dumps(update_list, indent = 4))
        self.output("Latest version found is {} {}".format(update['name'], update['version']))

        return update


    # Main
    def main(self):
        # Get the list of installers from the softwareupdate binary
        self.output("Querying software update for macOS installers")
        update = self.get_update()

        self.env["version"] = update['version']
        self.env["release"] = update['name']
        self.env["size"] = update['size']


if __name__ == "__main__":
    PROCESSOR = macOSReleaseProvider()
    PROCESSOR.execute_shell()