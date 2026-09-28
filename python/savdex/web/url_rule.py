"""
Правило url у Laravel — Str::isUrl: шаблон из Symfony UrlValidator 5.0.7
с флагами ~ixu. Нужен пакет regex: у встроенного re нет \\pL и
захватывающих квантификаторов PCRE.

Шаблон перенесён из vendor/laravel/framework/src/Illuminate/Support/Str.php
без правок. Как у PCRE без флага D, «$» пропускает и строку с одним
переводом строки в конце.
"""

# ruff: noqa: E501 — шаблон перенесён как есть

from __future__ import annotations

from functools import cache

import regex

#: Протоколы по умолчанию (Str::isUrl без $protocols)
PROTOCOLS = (
    "aaa|aaas|about|acap|acct|acd|acr|adiumxtra|adt|afp|afs|aim|amss|android|appdata|"
    "apt|ark|attachment|aw|barion|beshare|bitcoin|bitcoincash|blob|bolo|browserext|ca"
    "lculator|callto|cap|cast|casts|chrome|chrome-extension|cid|coap|coap\\+tcp|coap\\+"
    "ws|coaps|coaps\\+tcp|coaps\\+ws|com-eventbrite-attendee|content|conti|crid|cvs|dab"
    "|data|dav|diaspora|dict|did|dis|dlna-playcontainer|dlna-playsingle|dns|dntp|dpp|"
    "drm|drop|dtn|dvb|ed2k|elsi|example|facetime|fax|feed|feedready|file|filesystem|f"
    "inger|first-run-pen-experience|fish|fm|ftp|fuchsia-pkg|geo|gg|git|gizmoproject|g"
    "o|gopher|graph|gtalk|h323|ham|hcap|hcp|http|https|hxxp|hxxps|hydrazone|iax|icap|"
    "icon|im|imap|info|iotdisco|ipn|ipp|ipps|irc|irc6|ircs|iris|iris\\.beep|iris\\.lwz|"
    "iris\\.xpc|iris\\.xpcs|isostore|itms|jabber|jar|jms|keyparc|lastfm|ldap|ldaps|leap"
    "tofrogans|lorawan|lvlt|magnet|mailserver|mailto|maps|market|message|mid|mms|mode"
    "m|mongodb|moz|ms-access|ms-browser-extension|ms-calculator|ms-drive-to|ms-enroll"
    "ment|ms-excel|ms-eyecontrolspeech|ms-gamebarservices|ms-gamingoverlay|ms-getoffi"
    "ce|ms-help|ms-infopath|ms-inputapp|ms-lockscreencomponent-config|ms-media-stream"
    "-id|ms-mixedrealitycapture|ms-mobileplans|ms-officeapp|ms-people|ms-project|ms-p"
    "owerpoint|ms-publisher|ms-restoretabcompanion|ms-screenclip|ms-screensketch|ms-s"
    "earch|ms-search-repair|ms-secondary-screen-controller|ms-secondary-screen-setup|"
    "ms-settings|ms-settings-airplanemode|ms-settings-bluetooth|ms-settings-camera|ms"
    "-settings-cellular|ms-settings-cloudstorage|ms-settings-connectabledevices|ms-se"
    "ttings-displays-topology|ms-settings-emailandaccounts|ms-settings-language|ms-se"
    "ttings-location|ms-settings-lock|ms-settings-nfctransactions|ms-settings-notific"
    "ations|ms-settings-power|ms-settings-privacy|ms-settings-proximity|ms-settings-s"
    "creenrotation|ms-settings-wifi|ms-settings-workplace|ms-spd|ms-sttoverlay|ms-tra"
    "nsit-to|ms-useractivityset|ms-virtualtouchpad|ms-visio|ms-walk-to|ms-whiteboard|"
    "ms-whiteboard-cmd|ms-word|msnim|msrp|msrps|mss|mtqp|mumble|mupdate|mvn|news|nfs|"
    "ni|nih|nntp|notes|ocf|oid|onenote|onenote-cmd|opaquelocktoken|openpgp4fpr|pack|p"
    "alm|paparazzi|payto|pkcs11|platform|pop|pres|prospero|proxy|pwid|psyc|pttp|qb|qu"
    "ery|redis|rediss|reload|res|resource|rmi|rsync|rtmfp|rtmp|rtsp|rtsps|rtspu|s3|se"
    "condlife|service|session|sftp|sgn|shttp|sieve|simpleledger|sip|sips|skype|smb|sm"
    "s|smtp|snews|snmp|soap\\.beep|soap\\.beeps|soldat|spiffe|spotify|ssh|steam|stun|st"
    "uns|submit|svn|tag|teamspeak|tel|teliaeid|telnet|tftp|tg|things|thismessage|tip|"
    "tn3270|tool|ts3server|turn|turns|tv|udp|unreal|urn|ut2004|v-event|vemmi|ventrilo"
    "|videotex|vnc|view-source|wais|webcal|wpid|ws|wss|wtai|wyciwyg|xcon|xcon-userid|"
    "xfire|xmlrpc\\.beep|xmlrpc\\.beeps|xmpp|xri|ymsgr|z39\\.50|z39\\.50r|z39\\.50s"
)

_PATTERN = r"""^
            (LARAVEL_PROTOCOLS)://                                 # protocol
            (((?:[\_\.\pL\pN-]|%[0-9A-Fa-f]{2})+:)?((?:[\_\.\pL\pN-]|%[0-9A-Fa-f]{2})+)@)?  # basic auth
            (
                (?:
                    (?:
                        (?:[\pL\pN\pS\pM\-\_]++\.)+
                        (?:
                            (?:xn--[a-z0-9-]++)     # punycode in tld
                            |
                            (?:[\pL\pN\pM]++)       # no punycode in tld
                        )
                    )                               # a multi-level domain name
                        |
                    [a-z0-9\-\_]++                  # a single-level domain name
                )\.?
                    |                               # or
                \d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}  # an IP address
                    |                               # or
                \[
                    (?:(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){6})(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:::(?:(?:(?:[0-9a-f]{1,4})):){5})(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:(?:(?:(?:[0-9a-f]{1,4})))?::(?:(?:(?:[0-9a-f]{1,4})):){4})(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){0,1}(?:(?:[0-9a-f]{1,4})))?::(?:(?:(?:[0-9a-f]{1,4})):){3})(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){0,2}(?:(?:[0-9a-f]{1,4})))?::(?:(?:(?:[0-9a-f]{1,4})):){2})(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){0,3}(?:(?:[0-9a-f]{1,4})))?::(?:(?:[0-9a-f]{1,4})):)(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){0,4}(?:(?:[0-9a-f]{1,4})))?::)(?:(?:(?:(?:(?:[0-9a-f]{1,4})):(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9]))\.){3}(?:(?:25[0-5]|(?:[1-9]|1[0-9]|2[0-4])?[0-9])))))))|(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){0,5}(?:(?:[0-9a-f]{1,4})))?::)(?:(?:[0-9a-f]{1,4})))|(?:(?:(?:(?:(?:(?:[0-9a-f]{1,4})):){0,6}(?:(?:[0-9a-f]{1,4})))?::))))
                \]  # an IPv6 address
            )
            (:[0-9]+)?                              # a port (optional)
            (?:/ (?:[\pL\pN\-._\~!$&'()*+,;=:@]|%[0-9A-Fa-f]{2})* )*          # a path
            (?:\? (?:[\pL\pN\-._\~!$&'\[\]()*+,;=:@/?]|%[0-9A-Fa-f]{2})* )?   # a query (optional)
            (?:\# (?:[\pL\pN\-._\~!$&'()*+,;=:@/?]|%[0-9A-Fa-f]{2})* )?       # a fragment (optional)
        $"""


@cache
def _compiled(protocols: str) -> regex.Pattern[str]:
    return regex.compile(
        _PATTERN.replace("LARAVEL_PROTOCOLS", protocols),
        regex.IGNORECASE | regex.VERBOSE | regex.VERSION0,
    )


def is_url(value: object, protocols: tuple[str, ...] = ()) -> bool:
    """Str::isUrl."""
    if not isinstance(value, str):
        return False

    return _compiled("|".join(protocols) if protocols else PROTOCOLS).search(value) is not None
