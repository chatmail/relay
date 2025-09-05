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
