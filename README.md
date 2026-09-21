# File Share Bot – @TG_HINDI_ANIME69

When anyone starts the bot it replies:

> Hello, I am a file share bot of @TG_HINDI_ANIME69

Admins send files to the bot and get a shareable link. Anyone opening the link
receives the files.

## 1. Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Start your bot and send `/id` to get your Telegram user ID.
3. Set two environment variables:

| Variable    | Required | Description                                   |
|-------------|----------|-----------------------------------------------|
| `BOT_TOKEN` | yes      | Token from @BotFather                         |
| `ADMIN_IDS` | yes      | Comma-separated admin user IDs (who can upload) |
| `DATA_DIR`  | no       | Database folder (default `data`)              |

## 2. Run locally

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then edit .env
python bot.py
```

## 3. Deploy

**Render** – push this folder to GitHub, then *New → Blueprint* (uses `render.yaml`).
Add `BOT_TOKEN` and `ADMIN_IDS` when asked.

**Railway / Koyeb / any Docker host** – deploy from the repo (the `Dockerfile`
is detected automatically) and add the two environment variables.

**Heroku** – `heroku create`, set the config vars, deploy, then
`heroku ps:scale worker=1`. (Uses `Procfile` and `runtime.txt`.)

**VPS** – `docker build -t file-share-bot . && docker run -d --restart=always --env-file .env -v $(pwd)/data:/app/data file-share-bot`

The bot uses long polling, so no webhook or public URL setup is needed. If
`PORT` is set by the host, a tiny health-check server starts automatically.

> Run **only one** instance per bot token, otherwise Telegram returns a
> "Conflict" error.

## 4. Usage

- Send any file (document, video, audio, photo, GIF, voice) → get a link.
- `/batch` → send several files → `/done` → one link for all of them.
- `/cancel` cancels a batch, `/help` shows commands, `/id` shows your ID.

## Important: keep your links after redeploys

Links are stored in a SQLite file (`DATA_DIR/files.db`). Free tiers on Render,
Heroku, etc. have an ephemeral disk, so **the file is wiped on every redeploy/
restart** and old links stop working. Use a persistent disk/volume and point
`DATA_DIR` at it (e.g. `/data`) if you need permanent links.
