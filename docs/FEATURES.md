# Deco X60 — Local Management API surface (firmware 1.7.1)

Reverse-engineered, strictly local (no cloud). Transport: TDP→dropbear SSH:20001→TMP daemon.
Client: `deco_api.py`. Full read snapshot: `deco-snapshot.json`. Opcode map: `deco-opcodes.json`.

**48 reads confirmed working** on this hardware. Writes below are opcodes present in the app (not yet exercised).

## overview
- `R` **OPERATION_MODE_GET** `0x40a0` → ['fixed_wan_port', 'mode', 'modeList']
    - `W` OPERATION_MODE_BACKUP_SET `0x40a2`
    - `W` OPERATION_MODE_SET `0x40a1`
    - `W` OPERATION_MODE_SWITCH_NOT_ALERT_SET `0x43d2`
- `R` **LOCATION_GET** `0x400a` → ['support_plc', 'location', 'status']
- `R` **SYSTEM_TIME_GET** `0x427c` → ['tz_region', 'time', 'timezone']
    - `W` SYSTEM_TIME_SET `0x427d`
- `R` **INTERNET_GET** `0x400c`
- `R` **SPEEDTEST_INFO_GET** `0x4010` → ['down_speed', 'up_speed', 'last_speed_test_time', 'status']
    - `W` SPEEDTEST_START `0x4011`
- `R` **MONTHLY_REPORT_MGR_GET** `0x4222` → ['enable']
    - `W` MONTHLY_REPORT_MGR_SET `0x4223`
    - `W` MONTHLY_REPORT_REMOVE `0x4221`

## topology
- `R` **DEVICE_LIST_GET** `0x400f` → ['device_list']
    - `W` DEVICE_TOPOLOGY_SET `0x4091`
- `R` **DEVICE_LIST_SPEED_GET** `0x422f` → ['device_list_speed']
    - `W` DEVICE_TOPOLOGY_SET `0x4091`
- `R` **DEVICE_SIGNAL_LEVEL_LIST_GET** `0x4094` → ['device_list']

## clients
- `R` **CLIENT_LIST_GET** `0x4012` → ['speed_limit_count_max', 'priority_count_max', 'client_list']
    - `W` CLIENT_LIST_REMOVE `0x4090`
    - `W` CLIENT_LIST_SET `0x4013`
- `R` **CLIENT_LIST_SPEED_GET** `0x4014` → ['client_list_speed']
    - `W` CLIENT_LIST_REMOVE `0x4090`
    - `W` CLIENT_LIST_SET `0x4013`
- `R` **CLIENT_SPEED_GET** `0x4015` → ['client_list_speed']
    - `W` CLIENT_LIST_REMOVE `0x4090`
    - `W` CLIENT_LIST_SET `0x4013`
- `R` **CLIENT_ISOLATION_GET** `0x4302` → ['enable']
    - `W` CLIENT_LIST_REMOVE `0x4090`
    - `W` CLIENT_LIST_SET `0x4013`
- `R` **IOT_CLIENT_LIST_GET** `0x4040` → ['iot_count_per_cate_max', 'scan_wait_time', 'scan_status', 'iot_client_list']
    - `W` IOT_CLIENT_LIST_ADD `0x4042`
    - `W` IOT_CLIENT_LIST_MODIFY `0x4043`
    - `W` IOT_CLIENT_LIST_REMOVE `0x4041`
- `R` **IOT_PRODUCT_PROFILE_GET** `0x4045` → ['module_list']

## wireless
- `R` **WIRELESS_GET** `0x4009` → ['band5_1', 'band2_4']
    - `W` WIRELESS_SET `0x4008`
- `R` **WIFI_SCHEDULE_SETTINGS_GET** `0x43c2` → ['has_set_wifi_schedule', 'time_end', 'enable', 'time_begin', 'enable_band2_4']
    - `W` WIFI_SCHEDULE_SETTINGS_SET `0x43c3`
- `R` **BEAMFORMING_GET** `0x421b` → ['enable']
    - `W` BEAMFORMING_SET `0x421c`
- `R` **MAC_CLONE_GET** `0x4226` → ['enable']
    - `W` MAC_CLONE_SET `0x4227`
- `R` **MAC_CLONE_CLIENT_LIST_GET** `0x4293` → ['client_list']
    - `W` MAC_CLONE_SET `0x4227`

## network
- `R` **IPV4_GET** `0x4004` → ['wan', 'lan']
    - `W` IPV4_SET `0x4005`
- `R` **IPV6_GET** `0x4006` → ['enable_ipv6']
    - `W` IPV6_FIREWALL_LIST_ADD `0x4231`
    - `W` IPV6_SET `0x4007`
- `R` **IPV6_FIREWALL_LIST_GET** `0x4230` → ['firewall_list_limit', 'firewall_list']
    - `W` IPV6_FIREWALL_LIST_ADD `0x4231`
    - `W` IPV6_SET `0x4007`
- `R` **WAN_ISP_GET** `0x404e` → ['ipv6', 'vlan', 'ipv4']
    - `W` WAN_INFO_SET `0x407c`
    - `W` WAN_ISP_SET `0x404f`
    - `W` WAN_PROFILE_ADD `0x4058`
    - `W` WAN_PROFILE_DELETE `0x405a`
    - `W` WAN_PROFILE_MODIFY `0x4059`
- `R` **SMART_DHCP_GET** `0x4092` → ['enable']
    - `W` SMART_ANTENNA_SET `0x43a1`
    - `W` SMART_DHCP_SET `0x4093`
- `R` **IPTV_GET** `0x4224` → ['type', 'vlan_id', 'iptv_port', 'vlan_priority', 'enable']
    - `W` IPTV_NAT_INFO_SET `0x405c`
    - `W` IPTV_NAT_PROFILE_ADD `0x405e`
    - `W` IPTV_NAT_PROFILE_DELETE `0x4069`
    - `W` IPTV_NAT_PROFILE_MODIFY `0x405f`
    - `W` IPTV_SET `0x4225`
- `R` **SIP_ALG_GET** `0x421d` → ['enable']
    - `W` SIP_ALG_SET `0x421e`

## nat_forwarding
- `R` **PORT_FORWARDING_LIST_GET** `0x40b0` → ['port_forwarding_list_max_count', 'port_forwarding_list']
    - `W` PORT_FORWARDING_ADD `0x40b1`
    - `W` PORT_FORWARDING_DELETE `0x40b3`
    - `W` PORT_FORWARDING_MODIFY `0x40b2`
- `R` **IP_RESERVATION_LIST_GET** `0x40c0` → ['reservation_list_max_count', 'reservation_list']
    - `W` IPTV_NAT_INFO_SET `0x405c`
    - `W` IPTV_NAT_PROFILE_ADD `0x405e`
    - `W` IPTV_NAT_PROFILE_DELETE `0x4069`
    - `W` IPTV_NAT_PROFILE_MODIFY `0x405f`
    - `W` IPTV_SET `0x4225`
    - `W` IPV4_SET `0x4005`
    - `W` IPV6_FIREWALL_LIST_ADD `0x4231`
    - `W` IPV6_SET `0x4007`
    - `W` IP_MAC_BINDING_LIST_ADD `0x43f2`
    - `W` IP_MAC_BINDING_LIST_MODIFY `0x43f4`
    - `W` IP_MAC_BINDING_LIST_REMOVE `0x43f3`
    - `W` IP_MAC_BINDING_STATUS_SET `0x43f1`
    - `W` IP_RESERVATION_LIST_ADD `0x40c1`
    - `W` IP_RESERVATION_MODIFY `0x40c2`

## qos
- `R` **QOS_MODE_GET** `0x4036` → ['custom_detail', 'qos_mode']
    - `W` QOS_MODE_SET `0x4037`
- `R` **DPI_QOS_INFO_GET** `0x4378` → ['upstream_bandwidth', 'dpi_custom_mode_max_count', 'most_used_apps', 'has_set_dpi_qos', 'dpi_qos_mode_info', 'downstream_bandwidth', 'enable']
    - `W` DPI_QOS_INFO_SET `0x4379`
    - `W` DPI_QOS_MODE_ITEM_REMOVE `0x437a`
- `R` **BANDWIDTH_SWITCH_INFO_GET** `0x42f0` → ['band5', 'band2_4']
    - `W` BANDWIDTH_SWITCH_INFO_SET `0x42f1`
- `R` **BANDWIDTH_SWITCH_RESULT_GET** `0x42f2` → ['status']
    - `W` BANDWIDTH_SWITCH_INFO_SET `0x42f1`

## security
- `R` **SECURITY_INFO_GET** `0x403b` → ['db_update', 'modules_status', 'protected_days']
    - `W` SECURITY_HISTORY_CLEAR `0x403e`
    - `W` SECURITY_HISTORY_REMOVE `0x403f`
    - `W` SECURITY_INFO_SET `0x403c`
- `R` **SECURITY_HISTORY_GET** `0x403d` → ['history_list']
    - `W` SECURITY_HISTORY_CLEAR `0x403e`
    - `W` SECURITY_HISTORY_REMOVE `0x403f`
    - `W` SECURITY_INFO_SET `0x403c`
- `R` **AVIRA_ANTIVIRUS_GET** `0x4261` → ['enable']
    - `W` AVIRA_ANTIVIRUS_SET `0x4262`
    - `W` AVIRA_ANTIVIRUS_SETTINGS_SET `0x4268`
    - `W` AVIRA_FAMILY_CARE_OWNER_ADD `0x4271`
    - `W` AVIRA_FAMILY_CARE_OWNER_LIST_REMOVE `0x4272`
    - `W` AVIRA_SCAN_START_SET `0x4263`
    - `W` AVIRA_SCAN_STOP_SET `0x4264`
- `R` **AVIRA_ANTIVIRUS_SETTINGS_GET** `0x4267` → ['iot_protection', 'intrusion_prevention', 'web_protection']
    - `W` AVIRA_ANTIVIRUS_SET `0x4262`
    - `W` AVIRA_ANTIVIRUS_SETTINGS_SET `0x4268`
- `R` **ANTIVIRUS_ALLOWED_WEBSITES_GET** `0x4323` → ['website_list', 'max_count']
    - `W` ANTIVIRUS_ALLOWED_WEBSITES_ADD `0x4324`
    - `W` ANTIVIRUS_ALLOWED_WEBSITES_REMOVE `0x4325`
- `R` **ANTIVIRUS_WHITE_LIST_GET** `0x437b` → ['white_list', 'web_protection_max_count', 'iot_protection_max_count', 'intrusion_prevention_max_count']
    - `W` ANTIVIRUS_ALLOWED_WEBSITES_ADD `0x4324`
    - `W` ANTIVIRUS_ALLOWED_WEBSITES_REMOVE `0x4325`
    - `W` ANTIVIRUS_WHITE_LIST_ADD `0x437c`
    - `W` ANTIVIRUS_WHITE_LIST_REMOVE `0x437d`

## vpn
- `R` **WIREGUARDVPN_ACCOUNT_DEFAULT_GET** `0x436e` → ['allowed_server_ips', 'client_address']
- `R` **OPENVPN_CERT_GET** `0x436a` → ['cert_status']

## system
- `R` **REBOOT_SCHEDULE_GET** `0x42e0` → ['enable', 'setting']
    - `W` REBOOT_SCHEDULE_SET `0x42e1`
- `R` **FW_AUTO_UPDATE_GET** `0x427e` → ['enable_auto_update', 'time_begin', 'time_end']
    - `W` FW_AUTO_UPDATE_SET `0x427f`
- `R` **ECO_MODE_SETTINGS_GET** `0x43c0` → ['has_set_eco_mode', 'duration', 'power_mode', 'enable']
    - `W` ECO_MODE_ADVANCED_SETTINGS_SET `0x43cb`
    - `W` ECO_MODE_SETTINGS_SET `0x43c1`
    - `W` ECO_MODE_SKIP_SCHEDULE_SET `0x43c8`
- `R` **MANAGER_PERMISSION_GET** `0x4229` → ['permission_profile', 'manager_role_list']
    - `W` MANAGER_PERMISSION_SET `0x422a`
    - `W` MANAGER_PERMISSION_V2_REMOVE `0x4248`
    - `W` MANAGER_PERMISSION_V2_SET `0x4247`
- `R` **PRIVACY_POLICY_STATE_GET** `0x4385` → ['has_accepted_pp_list', 'accepted_pp_list']
    - `W` PRIVACY_POLICY_STATE_SET `0x4386`
- `R` **AUTOMATION_HISTORY_GET** `0x408c` → ['history_list']
    - `W` AUTOMATION_ACTION_ADD `0x4089`
    - `W` AUTOMATION_ACTION_LIST_REMOVE `0x408b`
    - `W` AUTOMATION_ACTION_MODIFY `0x408a`
    - `W` AUTOMATION_HISTORY_REMOVE `0x408d`
    - `W` AUTOMATION_TASK_LIST_MODIFY `0x408e`
    - `W` AUTOMATION_TRIGGER_ADD `0x4086`
    - `W` AUTOMATION_TRIGGER_LIST_REMOVE `0x4088`
    - `W` AUTOMATION_TRIGGER_MODIFY `0x4087`

## tools
- `R` **SPEEDTEST_SERVER_LIST_GET** `0x4228` → ['is_auto', 'server_list']
    - `W` SPEEDTEST_START `0x4011`
- `R` **TSS_LOCAL_DISCOVER_DEVICES_GET** `0x40a8` → ['tssReport']
    - `W` TSS_LOCAL_DISCOVER_DEVICES_SET `0x40a9`

## more reads (probed 2026-10-24)
The first sweep tried 131 reads. A second sweep on 2026-10-24 tried the remaining 108 `*_GET` opcodes:
51 work, 34 return an app error, and 23 a protocol error (not implemented on X60 1.7.1). The ones that work:

- `R` **11R_GET** `0x4208` -> ['enable']
- `R` **ACCESS_CONTROL_MODE_GET** `0x4401` -> ['access_control_mode', 'guest_network_access', 'new_device_notify']
- `R` **ACCESS_CONTROL_WHITE_LIST_GET** `0x4403` -> ['client_list', 'max_count']
- `R` **AUTOMATION_TASK_LIST_GET** `0x4080` -> ['task_count_max', 'trigger_count_max', 'task_list', 'action_count_max']
- `R` **AUTO_LED_GET** `0x401a` -> ['schedule', 'time_end', 'led_individual_control', 'enable', 'time_begin', 'enable_night_mode']
- `R` **AVIRA_FAMILY_CARE_FAMILY_TIME_GET** `0x4278` -> ['end_timestamp', 'time', 'client_list', 'enable', 'remaining_time']
- `R` **AVIRA_FEATURE_LIMIT_GET** `0x4330` -> ['family_care']
- `R` **BANDWIDTH_GET** `0x4219` -> ['upstream_bandwidth', 'has_set_bandwidth', 'downstream_bandwidth_max', 'downstream_bandwidth', 'upstream_bandwidth_max', 'enable']
- `R` **BLOCKED_LIST_GET** `0x4018` -> ['client_list', 'max_count']
- `R` **CAMERA_SECURITY_GET** `0x43be` -> ['local_only_mode', 'local_only_mode_camera_max_count', 'home_mode_camera_max_count', 'home_mode', 'trigger_client_max_count']
- `R` **CAPTIVE_PORTAL_GET** `0x43b9` -> ['time_limit', 'redirect_url', 'enable', 'login_page', 'authentication']
- `R` **CHECK_WIFI_STATUS_GET** `0x4098` -> ['state', 'max_waiting_time']
- `R` **CLIENT_LEASE_GET** `0x423d` -> ['client_lease']
- `R` **DDNS_GET** `0x40d0` -> ['ddns_enable', 'ddns_info', 'ap_changed']
- `R` **DEDICATED_BACKHAUL_GET** `0x4310` -> ['enable_5g2']
- `R` **DEVICE_LED_CATEGORY_GET** `0x42f7` -> ['device_list']
- `R` **DEVICE_RESOURCE_INFO_GET** `0x4317` -> ['device_list']
- `R` **DHCP_GET** `0x4213` -> ['ip_amount_in_use', 'end_ip', 'dns2', 'dns1', 'start_ip', 'gateway']
- `R` **DOH_DOT_GET** `0x43d0` -> ['enable', 'config', 'support_doh_url']
- `R` **DPI_APP_BLOCK_GET** `0x428b` -> ['app_block_list', 'version', 'all_return', 'need_up_to_date', 'amount']
- `R` **EASYMESH_GET** `0x4389` -> ['enable']
- `R` **EASY_MESH_WPS_GET** `0x438c` -> ['last_error_code', 'wps_state']
- `R` **FIXED_WAN_PORT_GET** `0x4242` -> ['fixed_wan_port', 'port_list', 'type', 'linked_port']
- `R` **FWLIST_LATEST_GET** `0x4301` -> ['fw_list']
- `R` **FW_LATEST_GET** `0x401c` -> ['fw_list']
- `R` **FW_PROG_GET** `0x401e` -> ['status', 'download_progress']
- `R` **FW_SYNC_GET** `0x4235` -> ['status']
- `R` **GA_INFO_LIST_GET** `0x4239` -> ['ga_info_list']
- `R` **HYBRID_MESH_COMPONENT_GET** `0x423e` -> ['device_list']
- `R` **HYBRID_MESH_INFO_GET** `0x42ec` -> ['backup_device_id', 'has_set_hybrid_mesh', 'component_list', 'enable', 'device_list']
- `R` **HY_OFFLINE_DETECTION_INFO_GET** `0x42ee` -> ['ping', 'detect_mode', 'dns']
- `R` **INTERNET_BACKUP_GET** `0x43e0` -> ['client_access', 'hotspot_count_max', 'speed_limit', 'enable', 'hotspot_list']
- `R` **IOT_OWNER_LIST_GET** `0x4060` -> ['owner_list', 'owner_count_max']
- `R` **IOT_SPACE_LIST_GET** `0x4050` -> ['space_count_max', 'space_list']
- `R` **IPV6_CLIENT_LIST_GET** `0x4234` -> ['client_list']
- `R` **LAN_IP_GET** `0x4211` -> ['lan_ip', 'dns_server_ip', 'wan_ip']
- `R` **MESSAGE_LIST_GET** `0x4028` -> ['message_list']
- `R` **MONTHLY_REPORT_GET** `0x40e0` -> list
- `R` **ONE_CLICK_HISTORY_GET** `0x4079` -> ['history_list']
- `R` **ONE_CLICK_LIST_GET** `0x4070` -> ['scene_count_max', 'alexa_scene_count_max', 'scene_list', 'action_count_max']
- `R` **QS_DISCOVERED_DEVICELIST_GET** `0x420a` -> ['max_discover_time', 'device_list', 'inet_status']
- `R` **ROUTE_STATIC_LIST_GET** `0x4294` -> ['route_static_list', 'max_count', 'interface']
- `R` **ROUTE_SYSTEM_LIST_GET** `0x4298` -> ['route_system_list']
- `R` **SYNC_CONFIG_GET** `0x4097` -> ['max_waiting_time', 'error_msg', 'error_code']
- `R` **UPNP_GET** `0x424a` -> ['enable']
- `R` **VLAN_GET** `0x420d` -> ['vlan']
- `R` **VPN_CLIENT_INFO_GET** `0x4370` -> ['enable', 'kill_enable', 'client_access', 'server_setting']
- `R` **VPN_CLIENT_SERVER_LIST_GET** `0x4372` -> ['max_count', 'server_list']
- `R` **VPN_SERVER_INFO_GET** `0x4360` -> ['vpn_server', 'server_config', 'server_list']
- `R` **WIRELESS_BANDWIDTH_ENHANCE_GET** `0x4251` -> ['enable_ht160']
- `R` **WPS_GET** `0x4215` -> ['wps_list', 'scanning_time']
