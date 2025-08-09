<img class="banner" src="collage-top.png"/>

/// tab | 🇬🇧 English

## Dear [Delta Chat](https://get.delta.chat) users and newcomers ...

{% if config.mail_domain != "nine.testrun.org" %}
Welcome to instant, interoperable and [privacy-preserving](privacy.html) messaging :) 
{% else %}
Welcome to the default onboarding server ({{ config.mail_domain }}) 
for Delta Chat users.  For details how it avoids storing personal information
please see our [privacy policy](privacy.html). 
{% endif %}

<a class="cta-button" href="DCACCOUNT:https://{{ config.mail_domain }}/new">Get a {{config.mail_domain}} chat profile</a>

If you are viewing this page on a different device
without a Delta Chat app,
you can also **scan this QR code** with Delta Chat:

<a href="DCACCOUNT:https://{{ config.mail_domain }}/new">
    <img width=300 style="float: none;" src="qr-chatmail-invite-{{config.mail_domain}}.png" /></a>

🐣 **Choose** your Avatar and Name

💬 **Start** chatting with any Delta Chat contacts using [QR invite codes](https://delta.chat/en/help#howtoe2ee)
///

/// tab | 🇷🇺 Русский

## Уважаемые пользователи и новички [Delta Chat](https://get.delta.chat)...

{% if config.mail_domain != "nine.testrun.org" %}
Добро пожаловать в мир мгновенного, совместимого и [конфиденциального](privacy.html) обмена сообщениями :) 
{% else %}
Вы находитесь на сервере по умолчанию ({{ config.mail_domain }}) 
для пользователей Delta Chat. Подробную информацию о том, как он избегает хранения личной информации,
см. в нашей [политике конфиденциальности](privacy.html). 
{% endif %}

<a class="cta-button" href="DCACCOUNT:https://{{ config.mail_domain }}/new">Создать чат-профиль на {{config.mail_domain}}</a>

Если вы открыли эту страницу на устройстве,
где нет приложения Delta Chat, вы можете
**отсканировать этот QR-код** с помощью Delta Chat:

<a href="DCACCOUNT:https://{{ config.mail_domain }}/new">
    <img width=300 style="float: none;" src="qr-chatmail-invite-{{config.mail_domain}}.png" /></a>

🐣 **Выберите** аватар и имя

💬 **Начните** чат с любыми контактами Delta Chat через [QR-приглашения](https://delta.chat/ru/help#howtoe2ee)
///

{% if config.is_development_instance == True %}
<div class="experimental">Note: this is only a temporary development chatmail service</div>
{% endif %}
