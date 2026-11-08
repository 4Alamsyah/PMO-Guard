"""Locks down browser DNS-over-HTTPS via Windows enterprise policy registry keys.

Without this, hosts-file blocking can be bypassed because Chrome/Edge/Firefox
can resolve domains themselves over DoH, ignoring the hosts file entirely.
Setting the official enterprise policy keys forces DoH off at the browser level.
"""
import winreg


def _set_value(hive, path, name, value, value_type=winreg.REG_SZ):
    key = winreg.CreateKeyEx(hive, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
    try:
        winreg.SetValueEx(key, name, 0, value_type, value)
    finally:
        winreg.CloseKey(key)


def apply_doh_lockdown():
    hive = winreg.HKEY_LOCAL_MACHINE

    # Chrome
    _set_value(hive, r"SOFTWARE\Policies\Google\Chrome", "DnsOverHttpsMode", "off")
    # Microsoft Edge
    _set_value(hive, r"SOFTWARE\Policies\Microsoft\Edge", "DnsOverHttpsMode", "off")
    # Brave (Chromium-based, same policy shape)
    _set_value(hive, r"SOFTWARE\Policies\BraveSoftware\Brave", "DnsOverHttpsMode", "off")
    # Firefox
    _set_value(hive, r"SOFTWARE\Policies\Mozilla\Firefox\DNSOverHTTPS", "Enabled", 0, winreg.REG_DWORD)
    _set_value(hive, r"SOFTWARE\Policies\Mozilla\Firefox\DNSOverHTTPS", "Locked", 1, winreg.REG_DWORD)
