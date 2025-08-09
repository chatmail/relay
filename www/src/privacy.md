<img class="banner" src="collage-privacy.png"/>

/// tab | 🇬🇧 English

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
///

/// tab | 🇷🇺 Русский

# Политика конфиденциальности для {{ config.mail_domain }}

{% if config.mail_domain == "nine.testrun.org" %}
Добро пожаловать на `{{config.mail_domain}}` — это основной сервер Chatmail для новых пользователей Delta Chat.  
Он поддерживается небольшой командой системных администраторов на добровольной основе.  
Альтернативные сервера вы можете найти [здесь](https://delta.chat/en/chatmail).  
{% endif %}

## Кратко: Личные данные не запрашиваются и не собираются

Этот сервер Chatmail не запрашивает и не сохраняет личную информацию.  
Серверы Chatmail существуют исключительно для надёжной передачи (временного хранения и доставки) зашифрованных сообщений между устройствами пользователей, использующих мессенджер Delta Chat.  

Технически, Chatmail-сервер можно представить как «маршрутизатор сообщений» с поддержкой сквозного шифрования в масштабе интернета.  

В отличие от классических почтовых сервисов (например, Gmail),  
Chatmail-серверы не запрашивают личные данные и не хранят письма постоянно.  
Они ближе по устройству к серверам Signal,  
однако не используют номера телефонов и могут безопасно и автоматически взаимодействовать как с другими Chatmail-серверами, так и с обычной электронной почтой.  

Отличия от традиционных почтовых серверов:

- безусловное удаление сообщений через {{ config.delete_mails_after }} дней;
- невозможность отправки незашифрованных сообщений;
- отсутствие хранения IP-адресов;
- IP-адреса не обрабатываются в связке с адресами электронной почты.

Из-за отсутствия обработки персональных данных  
данный сервер, возможно, формально не обязан иметь политику конфиденциальности.

Тем не менее, ниже приведена юридическая информация  
для удобства специалистов по защите данных и юристов, изучающих работу Chatmail.

---

## 1. Название и контактная информация

Ответственный за обработку ваших персональных данных:

```
{{ config.privacy_postal }}
```

Эл. почта: {{ config.privacy_mail }}

Назначен ответственный по защите данных:

```
{{ config.privacy_pdo }}
```

---

## 2. Обработка при использовании чата и электронной почты

Мы предоставляем сервисы, оптимизированные для работы с приложением [Delta Chat](https://delta.chat),  
и обрабатываем только те данные, которые необходимы для настройки и технической реализации доставки сообщений.  
Цель обработки — дать пользователям возможность читать, писать, управлять, удалять, отправлять и получать сообщения.  

Для этого мы используем серверное ПО, обеспечивающее передачу сообщений.

Обрабатываются следующие данные:

- Исходящие и входящие сообщения (SMTP) временно хранятся до их доставки получателю;
- Сообщения доступны получателю через IMAP до их удаления пользователем или по истечении установленного срока  
  (*обычно 4–8 недель*);
- Протоколы IMAP и SMTP защищены паролем, уникальным для каждого аккаунта;
- Пользователи могут самостоятельно просматривать или удалять сообщения через любой стандартный IMAP-клиент;
- Также возможно подключение к «службе передачи в реальном времени»,  
  которая устанавливает P2P-соединение между устройствами и позволяет отправлять временные сообщения,  
  которые *никогда* не сохраняются на сервере — даже в зашифрованном виде.

### 2.1 Создание аккаунта

Аккаунт создаётся одним из двух способов:

- с помощью QR-кода приглашения,  
  отсканированного через приложение Delta Chat;

- автоматически, при создании и регистрации аккаунта в {{ config.mail_domain }} через приложение Delta Chat.

В любом случае, обрабатывается только созданный адрес электронной почты.  
Номера телефонов, другие адреса электронной почты или любые другие идентификаторы не требуются.  
Правовое основание для обработки —  
статья 6 (1) пункт b Общего регламента по защите данных (GDPR),  
так как вы заключаете пользовательский договор, пользуясь нашим сервисом.

### 2.2 Обработка почтовых сообщений

Кроме того, мы обрабатываем данные,  
необходимые для обеспечения стабильной работы инфраструктуры сервера,  
доставки сообщений и предотвращения злоупотреблений.

- Поэтому может потребоваться обработка содержимого и/или метаданных  
  (например, заголовков писем и технической информации SMTP) во время передачи;

- Мы храним логи передаваемых сообщений ограниченное время —  
  они используются для устранения проблем с доставкой и ошибок ПО.

Также мы вводим ограничения для защиты системы от перегрузок:

- ограничения скорости (rate limits),
- лимиты на объём хранения,
- ограничения на размер сообщений,
- любые другие меры, необходимые для стабильной работы сервера и предотвращения злоупотреблений.

Обработка вышеуказанных данных необходима для предоставления сервиса.  
Правовое основание — статья 6 (1) пункт b GDPR.  
Обработка данных в целях безопасности и предотвращения злоупотреблений основана на статье 6 (1) пункт f GDPR,  
и соответствует нашим законным интересам.

Мы не используем собранные данные для определения вашей личности.

---

## 3. Обработка при посещении сайта

При посещении нашего сайта браузер вашего устройства  
автоматически передаёт определённую информацию на сервер,  
где она временно сохраняется в так называемых лог-файлах.  
Эти данные автоматически удаляются (обычно через *7 дней*).

Среди собираемых данных:

- тип используемого браузера,
- операционная система,
- дата и время доступа,
- страна и IP-адрес,
- запрашиваемый файл или ресурс,
- объём переданных данных,
- статус доступа (успешно, ошибка и т.п.),
- страница, с которой был сделан запрос.

Хостинг нашего сайта осуществляется внешним провайдером.  
Личные данные, собираемые на сайте, хранятся на его серверах.  
Провайдер обрабатывает данные строго по нашим инструкциям,  
в пределах заключённого договора на обработку данных (ст. 28 GDPR).

Цели обработки:

- обеспечение стабильного подключения к сайту;
- удобство использования сайта;
- контроль безопасности и стабильности системы;
- административные цели.

Правовое основание — статья 6 (1) пункт f GDPR.  
Собранные данные не используются для установления вашей личности.

---

## 4. Передача данных

Мы не сохраняем личные данные,  
но письма, ожидающие доставки, могут содержать личную информацию.  
Такие данные не передаются третьим лицам, за исключением следующих случаев:

a) при наличии вашего явного согласия (ст. 6 п.1 п. a GDPR);  

b) если передача необходима для защиты прав, интересов или правовой позиции (ст. 6 п.1 п. f GDPR);  

c) если это требуется по закону (ст. 6 п.1 п. c GDPR);  

d) если это необходимо для исполнения договора с вами (ст. 6 п.1 п. b GDPR);  

e) если обработка осуществляется сервис-провайдером по нашему поручению,  
   с которым заключён договор (ст. 28 GDPR),  
   предусматривающий меры безопасности и контроль с нашей стороны.

---

## 5. Права субъектов данных

Ваши права закреплены в статьях 12–23 GDPR.  
Так как сервер не хранит персональные данные — даже в зашифрованном виде —  
предоставление информации или подача возражений не требуются.  
Удаление данных можно выполнить напрямую через приложение Delta Chat.

Если у вас есть вопросы или жалобы, напишите нам:  
{{ config.privacy_mail }}

Также вы можете обратиться в надзорный орган по месту вашего проживания,  
работы или к органу, ответственному за нашу деятельность:  
`{{ config.privacy_supervisor }}`.

---

## 6. Актуальность политики конфиденциальности

Настоящая политика действует с *октября 2024 года*.  
В случае изменений в услугах или законодательства  
она может быть обновлена.
///
