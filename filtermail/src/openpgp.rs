//! OpenPGP payload checker.

use crate::error;
use base64::Engine;
use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;

/// Tries to get the byte `$idx` of the array slice `$payload`.
///
/// Returns [`error::Error::TruncatedHeader`] in the outer function, if `$idx` is out of range.
macro_rules! get_byte {
    ($payload:expr, $idx:expr) => {
        *$payload.get($idx).ok_or(error::Error::TruncatedHeader)?
    };
}

/// Checks the OpenPGP payload.
///
/// OpenPGP payload must consist only of `PKESK` and `SKESK` packets terminated by a single `SEIPD` packet.
///
/// Returns `Ok(true)` if OpenPGP payload is correct, `Ok(false)` otherwise.
///
/// # Errors
///
/// Returns an [`error::Error::TruncatedHeader`] if the OpenPGP packet header is truncated.
fn check_openpgp_payload(payload: &[u8]) -> Result<bool, error::Error> {
    // From RFC9580; we have to support legacy format too, for compatibility with GnuPG.
    //
    //                           +---------------+
    //   Encoded Packet Type ID: |7 6 5 4 3 2 1 0|
    //                           +---------------+
    //   OpenPGP format:
    //     Bit 7 -- always one
    //     Bit 6 -- always one
    //     Bits 5 to 0 -- Packet Type ID
    //
    //   Legacy format:
    //     Bit 7 -- always one
    //     Bit 6 -- always zero
    //     Bits 5 to 2 -- Packet Type ID
    //     Bits 1 to 0 -- length-type

    let mut i: usize = 0;
    while i < payload.len() {
        let bits_7_6 = get_byte!(payload, i) & 0xC0;
        // bit 6 is 0 for legacy (GnuPG)
        let legacy = if bits_7_6 == 0xC0 {
            false
        } else if bits_7_6 == 0x80 {
            true
        } else {
            log::debug!(
                "check_openpgp_payload: i={i} bits 7 and 6 doesn't indicate OpenPGP or legacy format"
            );
            return Ok(false);
        };

        let packet_type_id = if legacy {
            // bits 5 to 2
            (get_byte!(payload, i) & 0x3C) >> 2
        } else {
            // bits 5 to 0
            get_byte!(payload, i) & 0x3F
        };

        if legacy {
            // Body length calculation - Legacy, RFC9580 4.2.2

            let length_type = get_byte!(payload, i) & 0x03;
            i += 1;

            let body_len: usize;
            match length_type {
                0 => {
                    // One-octet length.
                    body_len = get_byte!(payload, i) as usize;
                    i += 1;
                }
                1 => {
                    // Two-octet length.
                    body_len = ((get_byte!(payload, i) as usize) << 8)
                        + (get_byte!(payload, i + 1) as usize);
                    i += 2;
                }
                2 => {
                    // Four-octet length.
                    body_len = ((get_byte!(payload, i) as usize) << 24)
                        + ((get_byte!(payload, i + 1) as usize) << 16)
                        + ((get_byte!(payload, i + 2) as usize) << 8)
                        + (get_byte!(payload, i + 3) as usize);
                    i += 4;
                }
                // 3 - indeterminate length, not supported
                // RFC9580 4.2.2:
                // "An implementation MUST NOT generate a Legacy format packet with indeterminate length."
                // We hope they don't.
                _ => {
                    log::debug!(
                        "check_openpgp_payload: i={i} Indeterminate length (3) length-type in legacy packet format"
                    );
                    return Ok(false);
                }
            };

            i += body_len;
        } else {
            // Body length calculation - OpenPGP, RFC9580 4.2.1

            i += 1;

            while get_byte!(payload, i) >= 224 && get_byte!(payload, i) < 255 {
                // Partial body length.
                let partial_length = 1usize << (get_byte!(payload, i) & 0x1F);
                i += 1 + partial_length;
            }

            let body_len: usize;
            if get_byte!(payload, i) < 192 {
                // One-octet length.
                body_len = get_byte!(payload, i) as usize;
                i += 1;
            } else if get_byte!(payload, i) < 224 {
                // Two-octet length.
                body_len = (((get_byte!(payload, i) as usize) - 192) << 8)
                    + (get_byte!(payload, i + 1) as usize)
                    + 192;
                i += 2;
            } else if get_byte!(payload, i) == 255 {
                // Five-octet length.
                body_len = ((get_byte!(payload, i + 1) as usize) << 24)
                    | ((get_byte!(payload, i + 2) as usize) << 16)
                    | ((get_byte!(payload, i + 3) as usize) << 8)
                    | (get_byte!(payload, i + 4) as usize);
                i += 5;
            } else {
                // Impossible, partial body length was processed above.
                log::debug!("check_openpgp_payload: i={i} Invalid body length");
                return Ok(false);
            }

            i += body_len;
        }

        if i == payload.len() {
            // Last packet should be
            // Symmetrically Encrypted and Integrity Protected Data Packet (SEIPD)
            //
            // This is the only place where this function may return `True`.
            log::debug!("check_openpgp_payload: i={i} packat_type_id={packet_type_id}");
            return Ok(packet_type_id == 18);
        } else if ![1, 3].contains(&packet_type_id) {
            // All packets except the last one must be either
            // Public-Key Encrypted Session Key Packet (PKESK)
            // or
            // Symmetric-Key Encrypted Session Key Packet (SKESK)
            log::debug!("check_openpgp_payload: i={i} packet_type_id={packet_type_id}");
            return Ok(false);
        }
    }

    Ok(false)
}

/// Check the armored PGP message for invalid content.
///
/// Returns `true` if the `payload` is a valid PGP message,
/// `outgoing` informs whether the message is outgoing or incoming
pub fn check_armored_payload(payload: &str, outgoing: bool) -> bool {
    const PREFIX: &str = "-----BEGIN PGP MESSAGE-----\r\n";
    let Some(payload) = payload.strip_prefix(PREFIX) else {
        log::debug!("check_armored_payload: Did not find PGP MESSAGE prefix");
        return false;
    };

    let payload = payload.trim_end_matches("\r\n");
    const SUFFIX: &str = "-----END PGP MESSAGE-----";
    let Some(mut payload) = payload.strip_suffix(SUFFIX) else {
        log::debug!("check_armored_payload: Did not find PGP MESSAGE suffix");
        return false;
    };

    const VERSION_COMMENT: &str = "Version: ";
    if payload.starts_with(VERSION_COMMENT) {
        // Disallow comments in outgoing messages
        if outgoing {
            log::debug!("check_armored_payload: Comment found in outgoing message");
            return false;
        }
        // Remove comments from incoming messages
        if let Some((_, right)) = payload.split_once("\r\n") {
            payload = right;
        }
    }

    let mut payload = payload.trim_start_matches("\r\n");

    // Remove CRC24.
    if let Some((left, _)) = payload.rsplit_once('=') {
        payload = left;
    }

    let payload = payload.replace(['\r', '\n'], "");
    let payload = match BASE64_STANDARD.decode(payload.as_bytes()) {
        Ok(v) => v,
        Err(_) => {
            log::debug!("check_armored_payload: Base64 decoding failed");
            return false;
        }
    };

    check_openpgp_payload(&payload).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::*;

    #[rstest]
    #[case::valid(r#"-----BEGIN PGP MESSAGE-----

wU4DhW3gBZ/VvCYSAQdA8bMs2spwbKdGjVsL1ByPkNrqD7frpB73maeL6I6SzDYg
O5G53tv339RdKq3WRcCtEEvxjHlUx2XNwXzC04BpmfvBTgNfPUyLDzjXnxIBB0Ae
8ymwGvXMCCimHXN0Dg8Ui62KOi03h0UgheoHWovJSCDF4CKre/xtFr3nL7lq/PKI
JsjVNz7/RK9FSXF6WwfONtLCyQGEuVAsB/KXfCBEyfKhaMwGHvhujRidGW5uV1no
lMGl3ODmo29Lgeu2uSE7EpJRZoe6hU6ddmBkqxax61ZtkaFlGFFpdo2K8balNNdz
ZsJ/9mmI9x3oOJ4/l1nhQbUO9ADbs7gJhFdV5Qkp30b5fCI7bU+aoe1ccBbLe/WM
YUty1PqcuQT7XjA+XmYuL261tvW8pBetT+i33/E2d8PzzYt2IuK9qeevyS+yxdwA
kfwejFWzzsUlJaDxs1x4XOxkMgSj+jo+g12dFOb7fyClsAnq23iDb8AuaT/BScAI
+lO+gher69+6LmM7VGHLG5k762J1jTaQCaKt1s8TAWV99Eo4491vL6fyvk3l/Cfg
RXSwiWFgj19Pn0Rq7CD9v22UE2vdUMBTcV4aw79mClk1YQ23jbF0y5DCjPdJ62Zo
tskBgFt3NoWV80jZ76zIBLrrjLwCCll8JjJtFwSkt2GX5RFBsVa4A8IDht9RtEk7
rrHgbSZQfkauEi/mH3/6CDZoLqSHudUZ7d4MaJwun1TkFYGe2ORwGJd4OBj3oGJp
H8YBwCpk///L/fKjX0Gg3M8nrpM4wrRFhPKidAgO/kcm25X4+ZHlVkWBTCt5RWKI
fHh6oLDZCqCfcgMkE1KKmwfIHaUkhq5BPRigwy6i5dh1DM4+1UCLh3dxzVbqE9b9
61NB19nXdRtDA2sOUnj9ve6m/wEPyCb6/zBQZqvCBYb1/AjdXpUrFT+DbpfyxaXN
XfhDVb5mNqNM/IVj0V5fvTc6vOfYbzQtPm10H+FdWWfb+rJRfyC3MA2w2IqstFe3
w3bu2iE6CQvSqRvge+ZqLKt/NqYwOURiUmpuklbl3kPJ97+mfKWoiqk8Iz1VY+bb
NMUC7aoGv+jcoj+WS6PYO8N6BeRVUUB3ZJSf8nzjgxm1/BcM+UD3BPrlhT11ODRs
baifGbprMWwt3dhb8cQgRT8GPdpO1OsDkzL6iikMjLHWWiA99GV6ruiHsIPw6boW
A6/uSOskbDHOROotKmddGTBd0iiHXAoQsJFt1ZjUkt6EHrgWs+GAvrvKpXs1mrz8
uj3GwEFrHS+Xuf2UDgpszYT3hI2cL/kUtGakVR7m7vVMZqXBUbZdGAEb1PZNPwsI
E4aMK02+EVB+tSN4Fzj99N2YD0inVYt+oPjr2tHhUS6aSGBNS/48Ki47DOg4Sxkn
lkOWnEbCD+XTnbDd
=agR5
-----END PGP MESSAGE-----"#, (true, true))]
    // GnuPG uses a legacy packet format that was obsoleted back in 1998 (RFC2440);
    // despite RFC9580 stating "The Legacy packet format SHOULD NOT be used to generate new data".
    #[case::gnupg(r#"-----BEGIN PGP MESSAGE-----

hF4DFYw3E47UG/ASAQdA3JnkJLJJALitYG/jzzEuF0p+hEBsgLTicaEJkJerInkw
SftuCMBjxv4D6rTqNkBn7IQh6gmlUKrUNBVEnq0V1InVF9o0kDpZfUUaB5ajNDMb
hF4DMiMKov7/CVgSAQdA7ib6HK7UVW2IdAM5PILbtqzuynukooXdg9YWWamjal8w
h/L0BxbtUFzI3U847dvzwtsW7A9CZXpi45OMXRC9mO3G/FAY1fW+C6PwObT7X1qK
0sDSAbyYddCihL1UEl6EigtD/YQezCTCydzstD2cRdV75lmUqzMCR8NbfvdttBbl
g04ZZtoHm1DSnXIAN4iFzW4EBgNVUDCnqO8wyYmWw4OCOt45IkTXGQUICGxeVh6g
4Pdj4OzSrg/mTZGIDjE2h/osVpPEQjwcAus73EZC4sz4n2U+OMHsq0M54Ds7wyGv
1KBzcQQ5Rc/DPPT0INnl58datm2HGKtWFWYab9/cw/fnQ+oYhmpkZbdITTmnTAyn
CHih86i0w6gXsX99iRLe6yP8BcU3rCCflsCp5zzlcFYViTPgEn1W8H32VOXulfcV
rpRFtc5yzjFj8Dvq9gI9yGIgqiS7oEAXdRBYhmBRTydMcbS1bCPDWy5w95Cp2VzR
x8cBq5e+27QTl9YNHr4xeric7del79wktJFiINzUCQPwkwM9ud2EJ1zN8Owr2Dp8
JvS2ioSEK5J2Lc95vDLmbVnMuKmVW6qD+fEdtYSHnSIc/t+iYG3GlaFyvO8t0Jav
cbsijrbYhoSOq67KseQWvfL+gL5u
=WWqc
-----END PGP MESSAGE-----"#, (true, true))]
    #[case::with_comment(r#"-----BEGIN PGP MESSAGE-----
Version: 1
wU4DhW3gBZ/VvCYSAQdA8bMs2spwbKdGjVsL1ByPkNrqD7frpB73maeL6I6SzDYg
O5G53tv339RdKq3WRcCtEEvxjHlUx2XNwXzC04BpmfvBTgNfPUyLDzjXnxIBB0Ae
8ymwGvXMCCimHXN0Dg8Ui62KOi03h0UgheoHWovJSCDF4CKre/xtFr3nL7lq/PKI
JsjVNz7/RK9FSXF6WwfONtLCyQGEuVAsB/KXfCBEyfKhaMwGHvhujRidGW5uV1no
lMGl3ODmo29Lgeu2uSE7EpJRZoe6hU6ddmBkqxax61ZtkaFlGFFpdo2K8balNNdz
ZsJ/9mmI9x3oOJ4/l1nhQbUO9ADbs7gJhFdV5Qkp30b5fCI7bU+aoe1ccBbLe/WM
YUty1PqcuQT7XjA+XmYuL261tvW8pBetT+i33/E2d8PzzYt2IuK9qeevyS+yxdwA
kfwejFWzzsUlJaDxs1x4XOxkMgSj+jo+g12dFOb7fyClsAnq23iDb8AuaT/BScAI
+lO+gher69+6LmM7VGHLG5k762J1jTaQCaKt1s8TAWV99Eo4491vL6fyvk3l/Cfg
RXSwiWFgj19Pn0Rq7CD9v22UE2vdUMBTcV4aw79mClk1YQ23jbF0y5DCjPdJ62Zo
tskBgFt3NoWV80jZ76zIBLrrjLwCCll8JjJtFwSkt2GX5RFBsVa4A8IDht9RtEk7
rrHgbSZQfkauEi/mH3/6CDZoLqSHudUZ7d4MaJwun1TkFYGe2ORwGJd4OBj3oGJp
H8YBwCpk///L/fKjX0Gg3M8nrpM4wrRFhPKidAgO/kcm25X4+ZHlVkWBTCt5RWKI
fHh6oLDZCqCfcgMkE1KKmwfIHaUkhq5BPRigwy6i5dh1DM4+1UCLh3dxzVbqE9b9
61NB19nXdRtDA2sOUnj9ve6m/wEPyCb6/zBQZqvCBYb1/AjdXpUrFT+DbpfyxaXN
XfhDVb5mNqNM/IVj0V5fvTc6vOfYbzQtPm10H+FdWWfb+rJRfyC3MA2w2IqstFe3
w3bu2iE6CQvSqRvge+ZqLKt/NqYwOURiUmpuklbl3kPJ97+mfKWoiqk8Iz1VY+bb
NMUC7aoGv+jcoj+WS6PYO8N6BeRVUUB3ZJSf8nzjgxm1/BcM+UD3BPrlhT11ODRs
baifGbprMWwt3dhb8cQgRT8GPdpO1OsDkzL6iikMjLHWWiA99GV6ruiHsIPw6boW
A6/uSOskbDHOROotKmddGTBd0iiHXAoQsJFt1ZjUkt6EHrgWs+GAvrvKpXs1mrz8
uj3GwEFrHS+Xuf2UDgpszYT3hI2cL/kUtGakVR7m7vVMZqXBUbZdGAEb1PZNPwsI
E4aMK02+EVB+tSN4Fzj99N2YD0inVYt+oPjr2tHhUS6aSGBNS/48Ki47DOg4Sxkn
lkOWnEbCD+XTnbDd
=agR5
-----END PGP MESSAGE-----"#, (false, true))]
    #[case::invalid_base64(r#"-----BEGIN PGP MESSAGE-----

wU4DhW3gBZ/VvCYSAQdA8bMs2spwbKdGjVsL1ByPkNrqD7frpB73maeL6I6SzDYg
O5G53tv339RdKq3WRcCtEEvxjHlUx2XNwXzC04BpmfvBTgNfPUyLDzjXnxIBB0Ae
8ymwGvXMCCimHXN0Dg8Ui62KOi03h0UgheoHWovJSCDF4CKre/xtFr3nL7lq/PKI
JsjVNz7/RK9FSXF6WwfONtLCyQGEuVAsB/KXfCBEyfKhaMwGHvhujRidGW5uV1no
lMGl3ODmo29Lgeu2uSE7EpJRZoe6hU6ddmBkqxax61ZtkaFlGFFpdo2K8balNNdz
ZsJ/9mmI9x3oOJ4/l1nhQbUO9ADbs7gJhFdV5Qkp30b5fCI7bU+aoe1ccBbLe/WM
YUty1PqcuQT7XjA+XmYuL261tvW8pBetT+i33/E2d8PzzYt2IuK9qeevyS+yxdwA
kfwejFWzzsUlJaDxs1x4XOxkMgSj+jo+g12dFOb7fyClsAnq23iDb8AuaT/BScAI
+lO+gher69+6LmM7VGHLG5k762J1jTaQCaKt1s8TAWV99Eo4491vL6fyvk3l/Cfg
RXSwiWFgj19Pn0Rq7CD9v22UE2vdUMBTcV4aw79mClk1YQ23jbF0y5DCjPdJ62Zo
tskBgFt3NoWV80jZ76zIBLrrjLwCCll8JjJtFwSkt2GX5RFBsVa4A8IDht9RtEk7
rrHgbSZQfkauEi/mH3/6CDZoLqSHudUZ7d4MaJwun1TkFYGe2ORwGJd4OBj3oGJp
H8YBwCpk///L/fKjX0Gg3M8nrpM4wrRFhPKidAgO/kcm25X4+ZHlVkWBTCt5RWKI
fHh6oLDZCqCfcgMkE1KKmwfIHaUkhq5BPRigwy6i5dh1DM4+1UCLh3dxzVbqE9b9
61NB19nXdRtDA2sOUnj9ve6m/wEPyCb6/zBQZqvCBYb1/AjdXpUrFT+DbpfyxaXN
XfhDVb5mNqNM/IVj0V5fvTc6vOfYbzQtPm10H+FdWWfb+rJRfyC3MA2w2IqstFe3
w3bu2iE6CQvSqRvge+ZqLKt/NqYwOURiUmpuklbl3kPJ97+mfKWoiqk8Iz1VY+bb
NMUC7aoGv+jcoj+WS6PYO8N6BeRVUUB3ZJSf8nzjgxm1/BcM+UD3BPrlhT11ODRs
baifGbprMWwt3dhb8cQgRT8GPdpO1OsDkzL6iikMjLHWWiA99GV6ruiHsIPw6boW
A6/uSOskbDHOROotKmddGTBd0iiHXAoQsJFt1ZjUkt6EHrgWs+GAvrvKpXs1mrz8
uj3GwEFrHS+Xuf2UDgpszYT3hI2cL/kUtGakVR7m7vVMZqXBUbZdGAEb1PZNPwsI
E4aMK02+EVB+tSN4Fzj99N2YD0inVYt+oPjr2tHhUS6aSGBNS/48Ki47DOg4Sxkn
lkOWnEbCD+XTnbDd=
=agR5
-----END PGP MESSAGE-----"#, (false, false))]
    #[case::invalid_non_pgp_base64(r#"-----BEGIN PGP MESSAGE-----

RGVsdGEgQ2hhdCBpcyBhIHJlbGlhYmxlLCBkZWNlbnRyYWxpemVkIGFuZCBzZWN1cmUgaW5zdGFu
dCBtZXNzYWdpbmcgYXBwLCBhdmFpbGFibGUgZm9yIG1vYmlsZSBhbmQgZGVza3RvcCBwbGF0Zm9y
bXMuCgogICAgSW5zdGFudCBjcmVhdGlvbiBvZiBwcml2YXRlIGNoYXQgcHJvZmlsZXMgd2l0aCBz
ZWN1cmUgYW5kIGludGVyb3BlcmFibGUgY2hhdG1haWwgcmVsYXlzIHRoYXQgb2ZmZXIgaW5zdGFu
dCBtZXNzYWdlIGRlbGl2ZXJ5LCBhbmQgUHVzaCBOb3RpZmljYXRpb25zIGZvciBpT1MgYW5kIEFu
ZHJvaWQgZGV2aWNlcy4KCiAgICBQZXJ2YXNpdmUgbXVsdGktcHJvZmlsZSBhbmQgbXVsdGktZGV2
aWNlIHN1cHBvcnQgb24gYWxsIHBsYXRmb3JtcyBhbmQgYmV0d2VlbiBkaWZmZXJlbnQgY2hhdG1h
aWwgYXBwcy4KCiAgICBJbnRlcmFjdGl2ZSBpbi1jaGF0IGFwcHMgZm9yIGdhbWluZyBhbmQgY29s
bGFib3JhdGlvbgoKICAgIEF1ZGl0ZWQgZW5kLXRvLWVuZCBlbmNyeXB0aW9uIHNhZmUgYWdhaW5z
dCBuZXR3b3JrIGFuZCBzZXJ2ZXIgYXR0YWNrcy4KCiAgICBGcmVlIGFuZCBPcGVuIFNvdXJjZSBz
b2Z0d2FyZSwgYm90aCBhcHAgYW5kIHNlcnZlciBzaWRlLCBidWlsdCBvbiBJbnRlcm5ldCBTdGFu
ZGFyZHMuCgo=
=4cf0a3
-----END PGP MESSAGE-----"#, (false, false))]
    #[case::invalid_cleartext(r#"-----BEGIN PGP MESSAGE-----

Definitely not base64 encoded PGP message content.
-----END PGP MESSAGE-----"#, (false, false))]
    #[case::invalid_no_begin(r#"-----END PGP MESSAGE-----"#, (false, false))]
    #[case::invalid_no_end(r#"-----BEGIN PGP MESSAGE-----"#, (false, false))]
    fn test_check_armored_payload(#[case] pgp_message: &str, #[case] expected: (bool, bool)) {
        let (expected_outgoing, expected_incoming) = expected;

        let result = check_armored_payload(&pgp_message.replace('\n', "\r\n"), true);
        assert_eq!(result, expected_outgoing);

        let result = check_armored_payload(&pgp_message.replace('\n', "\r\n"), false);
        assert_eq!(result, expected_incoming);
    }
}
