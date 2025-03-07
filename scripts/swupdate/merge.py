#!/usr/bin/python3.6
#
# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#

from s3confstore.cortx_s3_confstore import S3CortxConfStore
import os.path
import shutil
import sys

g_upgrade_items = {
  's3' : {
        'configFile' : "/opt/seagate/cortx/s3/conf/s3config.yaml",
        'oldSampleFile' : "/tmp/s3config.yaml.sample.old",
        'newSampleFile' : "/opt/seagate/cortx/s3/conf/s3config.yaml.sample",
        'unsafeAttributesFile' : "/opt/seagate/cortx/s3/conf/s3config_unsafe_attributes.yaml",
        'fileType' : 'yaml://'
    },
    'auth' : {
        'configFile' : "/opt/seagate/cortx/auth/resources/authserver.properties",
        'oldSampleFile' : "/tmp/authserver.properties.sample.old",
        'newSampleFile' : "/opt/seagate/cortx/auth/resources/authserver.properties.sample",
        'unsafeAttributesFile' : "/opt/seagate/cortx/auth/resources/authserver_unsafe_attributes.properties",
        'fileType' : 'properties://'
    },
    'keystore' : {
        'configFile' : "/opt/seagate/cortx/auth/resources/keystore.properties",
        'oldSampleFile' : "/tmp/keystore.properties.sample.old",
        'newSampleFile' : "/opt/seagate/cortx/auth/resources/keystore.properties.sample",
        'unsafeAttributesFile' : "/opt/seagate/cortx/auth/resources/keystore_unsafe_attributes.properties",
        'fileType' : 'properties://'
    },
    'bgdelete' : {
        'configFile' : "/opt/seagate/cortx/s3/s3backgrounddelete/config.yaml",
        'oldSampleFile' : "/tmp/config.yaml.sample.old",
        'newSampleFile' : "/opt/seagate/cortx/s3/s3backgrounddelete/config.yaml.sample",
        'unsafeAttributesFile' : "/opt/seagate/cortx/s3/s3backgrounddelete/s3backgrounddelete_unsafe_attributes.yaml",
        'fileType' : 'yaml://'
    },
    'cluster' : {
        'configFile' : "/opt/seagate/cortx/s3/s3backgrounddelete/s3_cluster.yaml",
        'oldSampleFile' : "/tmp/s3_cluster.yaml.sample.old",
        'newSampleFile' : "/opt/seagate/cortx/s3/s3backgrounddelete/s3_cluster.yaml.sample",
        'unsafeAttributesFile' : "/opt/seagate/cortx/s3/s3backgrounddelete/s3_cluster_unsafe_attributes.yaml",
        'fileType' : 'yaml://'
    }
}

def upgrade_config(configFile:str, oldSampleFile:str, newSampleFile:str, unsafeAttributesFile:str, filetype:str):
    """
    Core logic for updating config files during upgrade using conf store.
    Following is algorithm from merge:
    Iterate over all parameters sample.new file
    for every parameter, check
    - if it is marked as 'unsafe' in attributes file, skip
    - if it marked as 'safe' in the attributes file  
        - diff the value in config and sample.old - if it is changed, skip
        - if it is not changed,  we will overwrite the value in cfg file from sample.new
        - if it does not exist in cfg file add the value from sample.new file to cfg file
    - All the arrays in yaml are always overwritten
    """

    #If config file is not present then abort merging.
    if not os.path.isfile(configFile):
        sys.stderr.write(f'[cortx-s3server-rpm] ERROR: config file {configFile} does not exist\n')
        raise Exception(f'[cortx-s3server-rpm]  ERROR: config file {configFile} does not exist\n')

    # old sample file
    conf_old_sample = filetype + oldSampleFile
    cs_conf_old_sample = S3CortxConfStore(config=conf_old_sample, index=conf_old_sample)

    # new sample file
    conf_new_sample = filetype + newSampleFile
    cs_conf_new_sample = S3CortxConfStore(config=conf_new_sample, index=conf_new_sample)
    conf_new_sample_keys = cs_conf_new_sample.get_all_keys()

    # unsafe attribute file
    conf_unsafe_file = filetype + unsafeAttributesFile
    cs_conf_unsafe_file = S3CortxConfStore(config=conf_unsafe_file, index=conf_unsafe_file)
    conf_unsafe_file_keys = cs_conf_unsafe_file.get_all_keys()

    # active config file
    conf_file =  filetype + configFile
    cs_conf_file = S3CortxConfStore(config=conf_file, index=conf_file)
    conf_file_keys = cs_conf_file.get_all_keys()

    # Handle the special scenario where we have array in the config file
    # 1)search for keys with [] in config
    # 2)delete these keys/values in config
    for key in conf_new_sample_keys:
        if ((key.find('[') != -1) and (key.find(']') != -1)):
            # deleting key[0]..[n] has issues in confstore deletes
            # so deleting the root key which will deletes all the child entires
            cs_conf_file.delete_key(key[:key.find('[')], True)

    # deleted keys dont go away in already loaded index.
    # so we load at another index and re-populate conf_file_keys again.
    conf_file_keys_after_delete = S3CortxConfStore(config=conf_file, index=conf_file+"after_delete")
    conf_file_keys = conf_file_keys_after_delete.get_all_keys()

    #logic to determine which keys to merge.
    keys_to_overwrite = []
    for key in conf_new_sample_keys:
        #If key is marked for unsafe then do not modify/overwrite.
        if key in conf_unsafe_file_keys:
            continue
        #if key not present active config file then add it
        # (this will also add and hence effectively overwrite keys removed in above [] handing
        # and hence will always result in overwrite for these keys from the new sample file).
        if key not in conf_file_keys:
            keys_to_overwrite.append(key)
        #if key is not unsafe and value is not changed by user then overwrite it.
        elif cs_conf_file.get_config(key) == cs_conf_old_sample.get_config(key):
            keys_to_overwrite.append(key)
        #if user has changed the value of the key then skip it.
        else:
            continue

    cs_conf_file.merge_config(source_index=conf_new_sample, keys_to_include=keys_to_overwrite)
    cs_conf_file.save_config()
    sys.stdout.write(f'[cortx-s3server-rpm] INFO: config file {str(configFile)} upgraded successfully.\n')

if __name__ == "__main__":
    for upgrade_item in g_upgrade_items:
        upgrade_config(g_upgrade_items[upgrade_item]['configFile'],
            g_upgrade_items[upgrade_item]['oldSampleFile'],
            g_upgrade_items[upgrade_item]['newSampleFile'],
            g_upgrade_items[upgrade_item]['unsafeAttributesFile'],
            g_upgrade_items[upgrade_item]['fileType'])
