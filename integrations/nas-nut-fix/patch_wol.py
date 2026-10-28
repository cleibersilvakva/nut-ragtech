from patch_pi import replace_function


def patched(source):
    return replace_function(source, 'send_wol', '''def send_wol() -> None:
    from wol_transport import send_magic
    receipt = send_magic(NAS_MAC, interface="eth0")
    log.info("WOL aceito pela interface %s origem %s: %s pacotes para %s; aguardando NAS",
             receipt["interface"], receipt["source"], receipt["packets"], NAS_MAC)''')
