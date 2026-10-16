---
id: KB0001
title: VPN Troubleshooting
category: Network
---
# VPN Troubleshooting

Use this guide when the corporate VPN client will not connect, drops frequently, or authentication keeps failing.

## Authentication failures
1. Confirm your network password has not expired. Sign in to the employee portal; if it asks you to change your password, do that first and then reconnect the VPN.
2. Check that your account is not locked. Three wrong attempts in a row lock the account for 30 minutes.
3. Make sure the multi-factor authentication (MFA) prompt is approved on your phone. An unanswered MFA prompt causes "authentication failed".
4. Verify the date and time on your laptop are set automatically. A clock that is off by more than 5 minutes breaks certificate and MFA checks.
5. Sign out of the VPN client completely, then sign in again with your full email address as the username.

## Connection will not establish
1. Confirm you have working internet access without the VPN (open any public website).
2. Disconnect from guest or hotel Wi-Fi that uses a captive portal, sign in to the portal first, then start the VPN.
3. Switch the VPN gateway in the client settings to the second region (for example, from Primary to Backup).
4. Restart the VPN client. If that fails, reboot the laptop and try again.
5. Disable any third-party firewall or other VPN software that might block the VPN ports (UDP 443 and TCP 443).

## When to raise a ticket
If authentication still fails after the steps above, raise an incident with category Network / VPN. Include the exact error message, the time it started and whether other users nearby are affected. The Network Support team handles VPN incidents.
