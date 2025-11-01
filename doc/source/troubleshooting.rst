
Troubleshooting
========================================================

Disable automatic address creation
--------------------------------------------------------

If you need to stop address creation, e.g. because some script is wildly
creating addresses, login with ssh and run:

::

       touch /etc/chatmail-nocreate

Chatmail address creation will be denied while this file is present.


