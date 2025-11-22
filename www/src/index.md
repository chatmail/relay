
<img class="banner" src="collage-top.png"/>

## Dear [Delta Chat](https://get.delta.chat) users and newcomers ... 

{% if config.mail_domain != "nine.testrun.org" %}
Welcome to instant, interoperable and [privacy-preserving](privacy.html) messaging :) 
{% else %}
Welcome to the default onboarding server ({{ config.mail_domain }}) 
for Delta Chat users.  For details how it avoids storing personal information
please see our [privacy policy](privacy.html). 
{% endif %}

{% if config.allow_registrations != "yes" %}

This server does not allow {{config.allow_registrations}} for new registrations {{config}}

<a class="cta-button" href="https://delta.chat/en/chatmail">Find a Server that does</a>

{% else %}
<a class="cta-button" href="DCACCOUNT:https://{{ config.mail_domain }}/new">Get a {{config.mail_domain}} chat profile</a>

If you are viewing this page on a different device
without a Delta Chat app,
you can also **scan this QR code** with Delta Chat:

<a href="DCACCOUNT:https://{{ config.mail_domain }}/new">
    <img width=300 style="float: none;" src="qr-chatmail-invite-{{config.mail_domain}}.png" /></a>

🐣 **Choose** your Avatar and Name
{% endif %}

💬 **Start** chatting with any Delta Chat contacts using [QR invite codes](https://delta.chat/en/help#howtoe2ee)
