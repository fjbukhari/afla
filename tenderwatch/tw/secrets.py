"""Portal passwords live in the operating system's password store (Windows Credential Manager),
never in config files, the database or git."""
SERVICE = "tenderwatch"


def _kr():
    try:
        import keyring
        keyring.get_keyring()
        return keyring
    except Exception:  # no backend (e.g. bare WSL) -> manual login only
        return None


def get_login(source_id):
    kr = _kr()
    if not kr:
        return None, None
    try:
        return kr.get_password(SERVICE, f"{source_id}:user"), kr.get_password(SERVICE, f"{source_id}:pass")
    except Exception:
        return None, None


def set_login(source_id, user, password):
    kr = _kr()
    if not kr:
        raise SystemExit("No password store available here. Run Tender Watch from Windows (not WSL) to save "
                         "passwords, or just use 'login' to sign in by hand once.")
    kr.set_password(SERVICE, f"{source_id}:user", user)
    kr.set_password(SERVICE, f"{source_id}:pass", password)


def delete_login(source_id):
    kr = _kr()
    if kr:
        for k in ("user", "pass"):
            try:
                kr.delete_password(SERVICE, f"{source_id}:{k}")
            except Exception:
                pass
