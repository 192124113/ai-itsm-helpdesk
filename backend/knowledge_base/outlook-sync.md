---
id: KB0003
title: Outlook Synchronization Problems
category: Email
---
# Outlook Synchronization Problems

Use this guide when Outlook shows "Disconnected", "Trying to connect", messages are missing, or calendar and mailbox synchronization is stuck.

## Quick checks
1. Confirm the status bar at the bottom of Outlook shows "Connected". If it says "Working Offline", open the Send/Receive tab and turn off Work Offline.
2. Check you have internet access and, when working remotely, that the VPN is connected.
3. Check the Outlook web app in a browser. If the web app works, the problem is with the desktop client, not your mailbox.

## Troubleshoot Outlook synchronization
1. Close Outlook completely and reopen it. If it is not responding, end the Outlook task in Task Manager and restart it.
2. Press Send/Receive then "Update Folder" to force a folder synchronization.
3. Clear the Outlook cache: close Outlook, open the Mail control panel, choose the profile, and rename the offline data (.ost) file. Outlook rebuilds it on the next start. Large mailboxes can take an hour to resync.
4. Check that your mailbox is not full. A full mailbox stops new items arriving; archive old items or empty Deleted Items.
5. Create a new Outlook profile if the problem persists after a cache rebuild.

## Automation
Restarting Outlook and clearing the cache are approved for automated self-healing.

## When to raise a ticket
If the web app also fails or messages are missing from the server, raise an incident with category Email / Outlook for Messaging Support.
