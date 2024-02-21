from hashlib import md5
from pathlib import Path
from typing import Annotated, TYPE_CHECKING

import pyperclip
from rich import print
from rich.prompt import Prompt, Confirm

import typer

import cryptography
import models

if TYPE_CHECKING:
    from . import cryptography


storefile = Path(__file__).parent.joinpath("store.json").resolve()
app = typer.Typer(
    name="crypt",
    short_help="password manager",
    help="A simple password manager in your terminal",
    pretty_exceptions_show_locals=False,
)


def error(message: str, code: int = 1) -> None:
    print(f"[red][b]error:[reset] {message}")
    raise typer.Exit(code=code)


@app.command("init", short_help="create store", help="intionalizes a store with master password hash")
def register() -> None:
    if not storefile.exists():
        print(f"creating store file at [magenta][i]'{storefile}'")
        storefile.touch()

    elif not storefile.read_text() == "" and not Confirm.ask("[yellow]overwrite existing store"):
        error("overwrite permission denied", code=2)

    while True:
        master_passphrase = Prompt.ask(":locked_with_key: enter new master passphrase [magenta](must be at least 5 characters)", password=True)
        if len(master_passphrase) >= 5:
            break

        print("[prompt.invalid]passphrase too short")

    keyhash = md5(master_passphrase.encode()).hexdigest()
    print(f"passphrase signature: [b]{keyhash}")

    store = models.Store(keyhash=keyhash)
    store_json = store.model_dump_json(indent=2)

    storefile.write_text(store_json)
    print("[green][b]successfully initialized store")


@app.command("add", short_help="insert account", help="insert account with passphrase into the store")
def add(
    target: Annotated[str, typer.Argument(show_default=False, dir_okay=False, file_okay=False)],
    overwritable: Annotated[bool, typer.Option("--overwrite", "-o", show_default=False, is_flag=True)] = False,
) -> None:
    if not storefile.exists():
        error("store file not initialized", code=3)

    store = models.Store.model_validate_json(storefile.read_text())

    if store.accounts.__contains__(target) and not overwritable:
        error("account already exists", code=1)

    if overwritable and store.accounts.__contains__(target) and not Confirm.ask("[yellow]overwrite existing account"):
        error("overwrite permission denied", code=2)

    master_passphrase = Prompt.ask(":locked_with_key: enter master passphrase", password=True)
    if not md5(master_passphrase.encode()).hexdigest() == store.keyhash:
        error("incorrect master passphrase", code=4)

    passphrase = Prompt.ask(":pencil: enter account passphrase [magenta](should be at least 5 characters)", password=True)

    print(f"account passphrase signature: [b]{md5(passphrase.encode()).hexdigest()}")
    
    salt = cryptography.generate_salt()
    passphrase_iv = cryptography.generate_iv()
    passphrase = cryptography.encrypt(passphrase, master_passphrase, salt, passphrase_iv)

    account = models.Account(passphrase=passphrase, salt=salt, initial_vector=passphrase_iv)

    store.accounts[target] = account

    store_json = store.model_dump_json(indent=2)

    storefile.write_text(store_json)
    print(f"[green][b]successfully registered an account for [i]{target}")

@app.command("get", short_help="get account passphrase", help="get/print account passphrase from store")
def get(
    target: Annotated[str, typer.Argument(show_default=False, dir_okay=False, file_okay=False)],
    clipboard: Annotated[bool, typer.Option("--clipboard", "-c", show_default=False, is_flag=True)] = False,
) -> None:
    if not storefile.exists():
        error("store file not initialized", code=3)

    store = models.Store.model_validate_json(storefile.read_text())

    if not store.accounts.__contains__(target):
        error("account doesn't exists", code=1)

    master_passphrase = Prompt.ask(":locked_with_key: enter master passphrase", password=True)
    if not md5(master_passphrase.encode()).hexdigest() == store.keyhash:
        error("incorrect master passphrase", code=4)

    account = store.accounts[target]

    try:
        passphrase = cryptography.decrypt(account.passphrase, master_passphrase, account.salt, account.initial_vector)

    except BaseException:
        error("decryption failed, possibly because given master passphrase was not used at encryption", code=5)

    if not clipboard:
        print(f"[black]passphrase: [yellow][b]{passphrase}")
    else:
        pyperclip.copy(passphrase)
        print("[green][b]passphrase copied to clipboard")

@app.command("remove", short_help="remove account", help="remove an account from store")
def remove(
    target: Annotated[str, typer.Argument(show_default=False, dir_okay=False, file_okay=False)],
    ask: Annotated[bool, typer.Option("--no-input", "-ni", show_default=False, is_flag=True)] = True,
) -> None:
    if not storefile.exists():
        error("store file not initialized", code=3)

    store = models.Store.model_validate_json(storefile.read_text())

    if not store.accounts.__contains__(target):
        error("account doesn't exists", code=1)

    if ask and not Confirm.ask("[yellow]remove account from store"):
        error("delete permission not granted by user", code=2)

    store.accounts.pop(target)
    store_json = store.model_dump_json(indent=2)

    storefile.write_text(store_json)
    print(f"[green][b]account for {target} was removed from store")
