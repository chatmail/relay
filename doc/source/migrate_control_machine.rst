
Migrating to a new control machine
==================================

This tutorial demonstrates how to move your control machine safely or have multiple control machines.

Preliminary notes and assumptions
---------------------------------

- You have an existing working chatmail relay

- You already have ssh access to the machine

- You have a copy of your working `chatmail.ini` from the other machine

The steps to migrate control machines
-------------------------------------

1. **Save a copy of the working chatmail.ini**

   From your existing relay, make a copy of `chatmail.ini` for safekeeping,
   you will need this later


2. **Clone the chatmail relay repository to the new control machine**
   ::

       git clone https://github.com/chatmail/relay.git


3. **Create the chatmail.ini template with your previous working chatmail.ini**
   The `chatmail.ini` file you previously saved is now needed. 
   ::

       vim chatmail.ini

 
    
Paste the contents from the previously saved `chatmail.ini` and save


4. **Ensure you have rsync installed on your control machine**
   
   Rsync is required for pyinfra, ensure your new control machine has it installed.
  

5. **Setup virtual environments**
   ::

       ./scripts/initenv.sh

6. **Preflight checks for safety**

   Check existing dns recordset
   ::

       ./scripts/cmdeploy dns

   Check existing status
   ::

       ./scripts/cmdeploy status

   Deploy any updates or new changes
   ::

       ./scripts/cmdeploy run

   Conduct another set of checks just to be sure.

   Congrats! you have moved your control machine.  If you want to have multiple control machines
   simply ensure `chatmail.ini` is kept in sync between both machines.  It's recommended to commit this
   to version control.
