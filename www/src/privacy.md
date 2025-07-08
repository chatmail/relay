
# Privacy Policy for {{ config.mail_domain }} 

{% if config.mail_domain == "nine.testrun.org" %}
Welcome to `{{config.mail_domain}}`, the default chatmail onboarding server for Delta Chat users. 
It is operated on the side by a small sysops team
on a voluntary basis.
See [other chatmail servers](https://delta.chat/en/chatmail) for alternative server operators. 
{% endif %}


## Summary: No personal data asked or collected 

This chatmail server neither asks for nor retains personal information. 
Chatmail servers exist to reliably transmit (store and deliver) end-to-end encrypted messages
between user's devices running the Delta Chat messenger app. 
Technically, you may think of a Chatmail server as 
an end-to-end encrypted "messaging router" at Internet-scale. 

A chatmail server is very unlike classic e-mail servers (for example Google Mail servers)
that ask for personal data and permanently store messages. 
A chatmail server behaves more like the Signal messaging server 
but does not know about phone numbers and securely and automatically interoperates 
with other chatmail and classic e-mail servers. 

Unlike classic e-mail servers, this chatmail server 

- unconditionally removes messages after {{ config.delete_mails_after }} days,

- prohibits sending out un-encrypted messages,

- does not store Internet addresses ("IP addresses"), 

- does not process IP addresses in relation to email addresses.

Due to the resulting lack of personal data processing
this chatmail server may not require a privacy policy.

Nevertheless, we provide legal details below to make life easier
for data protection specialists and lawyers scrutinizing chatmail operations.



## 1. Name and contact information 

Responsible for the processing of your personal data is:
```
{{ config.privacy_postal }}
```

E-mail: {{ config.privacy_mail }}

We have appointed a data protection officer:

```
{{ config.privacy_pdo }}
```

## 2. Processing when using chat e-mail services

We provide services optimized for the use from [Delta Chat](https://delta.chat) apps
and process only the data necessary
for the setup and technical execution of message delivery.
The purpose of the processing is that users can
read, write, manage, delete, send, and receive chat messages.
For this purpose,
we operate server-side software
that enables us to send and receive messages.

We process the following data and details:

- Outgoing and incoming messages (SMTP) are stored for transit
  on behalf of their users until the message can be delivered.

- E-Mail-Messages are stored for the recipient and made accessible via IMAP protocols,
  until explicitly deleted by the user or until a fixed time period is exceeded,
  (*usually 4-8 weeks*).

- IMAP and SMTP protocols are password protected with unique credentials for each account.

- Users can retrieve or delete all stored messages
  without intervention from the operators using standard IMAP client tools.

- Users can connect to a "realtime relay service"
  to establish Peer-to-Peer connection between user devices,
  allowing them to send and retrieve ephemeral messages
  which are never stored on the chatmail server, also not in encrypted form.


### 2.1 Account setup

Creating an account happens in one of two ways on our mail servers: 

- with a QR invitation token 
  which is scanned using the Delta Chat app
  and then the account is created.

- by letting Delta Chat otherwise create an account 
  and register it with a {{ config.mail_domain }} mail server. 

In either case, we process the newly created email address.
No phone numbers,
other email addresses,
or other identifiable data
is currently required.
The legal basis for the processing is
Art. 6 (1) lit. b GDPR,
as you have a usage contract with us
by using our services.

### 2.2 Processing of E-Mail-Messages

In addition,
we will process data
to keep the server infrastructure operational
for purposes of e-mail dispatch
and abuse prevention.

- Therefore,
  it is necessary to process the content and/or metadata
  (e.g., headers of the email as well as smtp chatter)
  of E-Mail-Messages in transit. 

- We will keep logs of messages in transit for a limited time.
  These logs are used to debug delivery problems and software bugs.

In addition,
we process data to protect the systems from excessive use.
Therefore, limits are enforced:

- rate limits

- storage limits

- message size limits

- any other limit necessary for the whole server to function in a healthy way
  and to prevent abuse.

The processing and use of the above permissions
are performed to provide the service.
The data processing is necessary for the use of our services,
therefore the legal basis of the processing is
Art. 6 (1) lit. b GDPR,
as you have a usage contract with us
by using our services.
The legal basis for the data processing
for the purposes of security and abuse prevention is
Art. 6 (1) lit. f GDPR.
Our legitimate interest results
from the aforementioned purposes.
We will not use the collected data
for the purpose of drawing conclusions
about your person.


## 3. Processing when using our Website

When you visit our website,
the browser used on your end device
automatically sends information to the server of our website.
This information is temporarily stored in a so-called log file.
The following information is collected and stored
until it is automatically deleted
(*usually 7 days*):

- used type of browser,

- used operating system, 

- access date and time as well as

- country of origin and IP address, 

- the requested file name or HTTP resource,

- the amount of data transferred,

- the access status (file transferred, file not found, etc.) and

- the page from which the file was requested.

This website is hosted by an external service provider (hoster).
The personal data collected on this website is stored
on the hoster's servers.
Our hoster will process your data
only to the extent necessary to fulfill its obligations
to perform under our instructions.
In order to ensure data protection-compliant processing,
we have concluded a data processing agreement with our hoster.

The aforementioned data is processed by us for the following purposes:  

- Ensuring a reliable connection setup of the website,

- ensuring a convenient use of our website,

- checking and ensuring system security and stability, and

- for other administrative purposes.

The legal basis for the data processing is
Art. 6 (1) lit. f GDPR.
Our legitimate interest results
from the aforementioned purposes of data collection.
We will not use the collected data
for the purpose of drawing conclusions about your person.

## 4. Transfer of Data

We do not retain any personal data but e-mail messages waiting to be delivered 
may contain personal data.
Any such residual personal data will not be transferred to third parties
for purposes other than those listed below:

a) you have given your express consent
in accordance with Art. 6 para. 1 sentence 1 lit. a GDPR,  

b) the disclosure is necessary for the assertion, exercise or defence of legal claims
pursuant to Art. 6 (1) sentence 1 lit. f GDPR
and there is no reason to assume that you have
an overriding interest worthy of protection
in the non-disclosure of your data,  

c) in the event that there is a legal obligation to disclose your data
pursuant to Art. 6 para. 1 sentence 1 lit. c GDPR,
as well as  

d) this is legally permissible and necessary
in accordance with Art. 6 Para. 1 S. 1 lit. b GDPR
for the processing of contractual relationships with you,  

e) this is carried out by a service provider
acting on our behalf and on our exclusive instructions,
whom we have carefully selected (Art. 28 (1) GDPR)
and with whom we have concluded a corresponding contract on commissioned processing (Art. 28 (3) GDPR),
which obliges our contractor,
among other things,
to implement appropriate security measures
and grants us comprehensive control powers.

## 5. Rights of the data subject

The rights arise from Articles 12 to 23 GDPR.
Since no personal data is stored on our servers,
even in encrypted form,
there is no need to provide information
on these or possible objections.
A deletion can be made
directly in the Delta Chat email messenger.

If you have any questions or complaints, 
please feel free to contact us by email:  
{{ config.privacy_mail }}

As a rule, you can contact the supervisory authority of your usual place of residence
or workplace
or our registered office for this purpose.
The supervisory authority responsible for our place of business
is the `{{ config.privacy_supervisor }}`.


## 6. Validity of this privacy policy 

This data protection declaration is valid
as of *October 2024*.
Due to the further development of our service and offers
or due to changed legal or official requirements,
it may become necessary to revise this data protection declaration from time to time.


