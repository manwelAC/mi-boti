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

## Manual Philippines discovery — 2026-11-16

Local extract discovery can now be explicitly enabled after preparation. Keep the example policy disabled by default. To prepare or refresh a snapshot, run `.venv\Scripts\python.exe -m mi_boti import-ph-extract`, then `.venv\Scripts\python.exe -m mi_boti verify-ph-extract`. These commands fetch/import only when invoked and never register businesses. The importer retains the previous generation if refresh fails. Snapshot data is not live website evidence; observation timestamps and partial-coverage limitations remain visible in persisted provenance.

After successful verification, enable only `[sources.philippines_extract]` in ignored config.toml and restart the bot through the existing local launcher. The approved fixed endpoint and current policy are validated; public Overpass, arbitrary sources and all AI providers stay blocked. In lead-discovery, use `/discover campaign_id:<saved campaign UUID> limit:10`. Only that authorized command registers observations. The command first returns a job receipt, then a result summary. Use `/lead` for ambiguity reviews. No AI, qualification or hunting is started. Website collection is Phase 4a, not part of this snapshot lookup.

To reopen saved discovery output without searching again, use `/discover job_id:<job UUID>` in lead-discovery. The private results card lists up to ten observations per page and includes an inspection dropdown for source details. The controls expire after ten minutes; rerun the same command to reopen them. A new business is not a qualified lead, and snapshot assertions are not current website research.

## Website research walkthrough

Use business-research. Research is provider-free and never qualifies a lead or sends outreach.

1. Choose a discovered business and identify its official public website. A missing URL is unknown; Mi Boti does not guess a domain. Inspect the site's terms/access policy for this intended collection.
2. As owner/administrator, run `/research action:review business:<UUID> url:<official URL> permission_url:<same-host permission reference> rationale:<what permits this collection>`. Read and confirm the private preview. This records a seven-day review, not a fetch or a legal conclusion. Unavailable/disallowed robots policy still prevents collection.
3. Run `/research business:<UUID> refresh:true`. It returns a job ID, then a saved-evidence card after bounded collection. Website observations are timestamped excerpts with limitations, not AI conclusions.
4. Reopen with `/research action:status job_id:<UUID>`. Use `action:cancel job_id:<UUID>` to stop work. Administrators can `action:revoke business:<UUID>` to remove current access. Evidence already committed remains immutable.

Configure research.user_agent locally with a descriptive contact reference; the ignored deployment config now uses the Mi Boti repository URL. No bot token is needed for local HTTP configuration. Restart the existing bot to synchronize the new /research options. No second bot or real-server setup was launched by development. Live Discord research remains a required owner check.
