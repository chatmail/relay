
<img class="banner" src="collage-top.png"/>

## Dear [Delta Chat](https://get.delta.chat) users and newcomers ... 

{% if config.mail_domain != "nine.testrun.org" %}
Welcome to instant, interoperable and [privacy-preserving](privacy.html) messaging :) 
{% else %}
Welcome to the default onboarding server ({{ config.mail_domain }}) 
for Delta Chat users.  For details how it avoids storing personal information
please see our [privacy policy](privacy.html). 
{% endif %}

{% if config.tls_cert_mode == "self" %}
<a class="cta-button" id="dclogin-link" href="#">Get a {{config.mail_domain}} chat profile</a>

If you are viewing this page on a different device
without a Delta Chat app,
you can also **scan this QR code** with Delta Chat:

<a id="qr-link" href="#"><div id="qr-code"></div></a>

<script src="qrcode-svg.min.js"></script>
<script src="dclogin.js"></script>
{% else %}
<a class="cta-button" href="DCACCOUNT:{{ config.mail_domain }}">Get a {{config.mail_domain}} chat profile</a>

If you are viewing this page on a different device
without a Delta Chat app,
you can also **scan this QR code** with Delta Chat:

<a href="DCACCOUNT:{{ config.mail_domain }}">
    <img width=300 style="float: none;" src="qr-chatmail-invite-{{config.mail_domain}}.png" /></a>
{% endif %}

🐣 **Choose** your Avatar and Name

💬 **Start** chatting with any Delta Chat contacts using [QR invite codes](https://delta.chat/en/help#howtoe2ee)
