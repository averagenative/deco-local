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
