# Local operations

Operator reference for the existing Mi Boti deployment. Product identity and milestone status live in the [README](../README.md); configuration remains governed by [doc 23](23-IMPLEMENTATION-GUIDELINES.md).

## Local environment and launch

Run these commands from the repository folder using the verified Windows / CPython 3.14 environment. The bot now supports Phase 2 setup and authorization; discovery, research, CRM and AI execution remain unavailable.

### 1. Create the environment

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Package metadata permits Python **3.11–3.14**; only **3.14.6 on Windows** has been verified. Direct pins are discord.py 2.7.1, HTTPX 0.28.1, BeautifulSoup 4.15.0, and pytest 9.2.0 for development.

<details>
<summary><strong>Use the exact verified Windows / Python 3.14 dependency set</strong></summary>

Install the resolved dependencies before installing the editable project:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-py314-windows.txt
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The lock file is specific to the verified environment. Other Python versions and operating systems require their own verification.

</details>

### 2. Check configuration without credentials

```powershell
$env:MI_BOTI_CONFIG_FILE = (Resolve-Path config.example.toml).Path
.venv\Scripts\python.exe -m mi_boti check-config
```

This reports configuration status without creating runtime data, connecting Discord, starting workers, or running AI. Copy `config.example.toml` to ignored `config.toml` when preparing local settings; the complete configuration contract is in [doc 23](23-IMPLEMENTATION-GUIDELINES.md).

### 3. Run the tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests use synthetic guild/owner IDs and fresh confined directories under ignored `.pytest_cache`. They do not contact Discord, public websites, or an AI account.

<details>
<summary><strong>Initialize a real local database</strong></summary>

Before initialization, supply the intended `MI_BOTI_GUILD_ID` and `MI_BOTI_OWNER_IDS` locally. Then run:

```powershell
.venv\Scripts\python.exe -m mi_boti init-db
```

Initialization validates identity, holds the deployment lock, applies migrations, and binds the database to the configured guild. It does not connect Discord or execute jobs. Repeating initialization is safe; changing the guild binding is rejected. Use a dedicated data directory because startup refuses unrelated contents and applies private permissions.

The future Discord connection additionally requires `MI_BOTI_DISCORD_TOKEN`. Keep the token in the local environment—never in TOML, documentation, source control, or chat.

</details>

### 4. Connect the bot and preview server setup

The prepared local `run-local.ps1` uses the deployment IDs supplied by the operator and is ignored by Git. If the local launcher must be restored, copy [run-local.example.ps1](../run-local.example.ps1) to `run-local.ps1`; the template requests the nonsecret IDs interactively.

```powershell
.\run-local.ps1
```

Enter the **regenerated bot token at the masked local prompt**. The launcher saves it with Windows account-bound encryption under `%LOCALAPPDATA%\MiBoti\credentials`, outside the project, and reuses it on later starts. Run `.\run-local.ps1 -ResetToken` to replace the saved token after rotation. It is never saved to configuration or source. Leave that terminal running; press Ctrl+C for a controlled shutdown. The bot must be invited with `bot` and `applications.commands` scopes and the permissions listed in [doc 06](06-DISCORD-SERVER-ARCHITECTURE.md). It does not require Administrator, Message Content intent, or an inbound public endpoint/public key.

As the configured owner or a server administrator, run `/setup` in a server text channel. Review the private resource/permission preview and press **Confirm setup** only when it matches your intent. No categories, channels or panels are created before confirmation. Repeating setup reuses persisted IDs; deleted or uncertain resources require another approved recovery preview. Once configured, operational commands enforce their assigned channel IDs. Unimplemented workflows explicitly reject execution without creating jobs.

For an already configured environment, `.venv\Scripts\python.exe -m mi_boti run` uses `MI_BOTI_DISCORD_TOKEN`, `MI_BOTI_GUILD_ID`, `MI_BOTI_OWNER_IDS` and optional `MI_BOTI_APPLICATION_ID`. The application ID is checked before command synchronization. No hunting or setup runs automatically at startup/reconnect. Live acceptance is tracked in doc 22; never paste tokens into chat.

## Inspect the Phase 2 prerequisite checkpoint

```powershell
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
```

This reads local SQLite state only. It checks integrity, READY configuration, resource parents, canonical mapping coverage and persistent panel records without creating work, accessing credentials or contacting Discord. The bot may remain running. `full_phase2_accepted` deliberately remains false because this tool cannot verify live interactions or role/resource recovery. Review the [roadmap checkpoint](21-DEVELOPMENT-ROADMAP.md#phase-3-prerequisite-checkpoint--2026-11-14) for the manual gates.
