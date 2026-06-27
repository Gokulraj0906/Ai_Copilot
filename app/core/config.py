# from pydantic_settings import BaseSettings


# class Settings(BaseSettings):
#     # ── Core infrastructure ───────────────────────────────────────────────────
#     openrouter_api_key: str
#     database_url: str 
#     redis_url: str

#     # ── Messaging ─────────────────────────────────────────────────────────────
#     slack_bot_token: str = ""                  # xoxb-...
#     discord_bot_token: str = ""                # Bot token from Discord dev portal
#     telegram_bot_token: str = ""               # From @BotFather
#     twilio_account_sid: str = ""
#     twilio_auth_token: str = ""
#     twilio_from_number: str = ""               # +1234567890
#     sendgrid_api_key: str = ""                 # SG.xxx
#     smtp_host: str = "smtp.gmail.com"
#     smtp_port: int = 587
#     smtp_user: str = ""
#     smtp_password: str = ""
#     smtp_from: str = ""
#     whatsapp_api_url: str = "https://graph.facebook.com/v18.0"
#     whatsapp_access_token: str = ""            # Meta permanent/long-lived token
#     firebase_server_key: str = ""              # FCM server key

#     # ── Productivity / Docs ───────────────────────────────────────────────────
#     notion_api_key: str = ""                   # secret_xxx
#     google_service_account_json: str = ""      # Path to service account JSON file
#     airtable_api_key: str = ""                 # patXXX
#     jira_domain: str = ""                      # yourcompany.atlassian.net
#     jira_email: str = ""
#     jira_api_token: str = ""
#     trello_api_key: str = ""
#     trello_api_token: str = ""
#     linear_api_key: str = ""                   # lin_api_xxx
#     github_token: str = ""                     # ghp_xxx or fine-grained PAT

#     # ── CRM / Support ─────────────────────────────────────────────────────────
#     hubspot_access_token: str = ""             # pat-na1-xxx
#     salesforce_client_id: str = ""
#     salesforce_client_secret: str = ""
#     salesforce_username: str = ""
#     salesforce_password: str = ""
#     salesforce_security_token: str = ""
#     zoho_client_id: str = ""
#     zoho_client_secret: str = ""
#     zoho_refresh_token: str = ""
#     freshdesk_domain: str = ""                 # yourcompany.freshdesk.com
#     freshdesk_api_key: str = ""
#     zendesk_subdomain: str = ""
#     zendesk_email: str = ""
#     zendesk_api_token: str = ""

#     # ── Payments ─────────────────────────────────────────────────────────────
#     razorpay_key_id: str = ""
#     razorpay_key_secret: str = ""
#     stripe_secret_key: str = ""               # sk_live_xxx or sk_test_xxx

#     # ── Logistics ────────────────────────────────────────────────────────────
#     delhivery_api_token: str = ""
#     delhivery_api_url: str = "https://track.delhivery.com"
#     shiprocket_email: str = ""
#     shiprocket_password: str = ""

#     # ── Cloud / Storage ───────────────────────────────────────────────────────
#     aws_access_key_id: str = ""
#     aws_secret_access_key: str = ""
#     aws_region: str = "ap-south-1"

#     # ── Calendar / Meetings ───────────────────────────────────────────────────
#     zoom_account_id: str = ""
#     zoom_client_id: str = ""
#     zoom_client_secret: str = ""

#     # ── Social / Marketing ────────────────────────────────────────────────────
#     twitter_bearer_token: str = ""
#     twitter_api_key: str = ""
#     twitter_api_secret: str = ""
#     twitter_access_token: str = ""
#     twitter_access_secret: str = ""
#     mailchimp_api_key: str = ""               # key-us21
#     mailchimp_server_prefix: str = ""         # us21
#     jwt_secret: str
#     encryption_master_key: str

#     class Config:
#     #     env_file = ".env"
#         model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# settings = Settings()
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Core infrastructure ───────────────────────────────────────────────────
    openrouter_api_key: str
    database_url: str = "postgresql+asyncpg://copilot:copilot@localhost:5433/copilot"
    redis_url: str = "redis://localhost:6379"

    # ── Messaging ─────────────────────────────────────────────────────────────
    slack_bot_token: str = ""                  # xoxb-...
    discord_bot_token: str = ""                # Bot token from Discord dev portal
    telegram_bot_token: str = ""               # From @BotFather
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""               # +1234567890
    sendgrid_api_key: str = ""                 # SG.xxx
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    whatsapp_api_url: str = "https://graph.facebook.com/v18.0"
    whatsapp_access_token: str = ""            # Meta permanent/long-lived token
    firebase_server_key: str = ""              # FCM server key

    # ── Productivity / Docs ───────────────────────────────────────────────────
    notion_api_key: str = ""                   # secret_xxx
    google_service_account_json: str = ""      # Path to service account JSON file
    airtable_api_key: str = ""                 # patXXX
    jira_domain: str = ""                      # yourcompany.atlassian.net
    jira_email: str = ""
    jira_api_token: str = ""
    trello_api_key: str = ""
    trello_api_token: str = ""
    linear_api_key: str = ""                   # lin_api_xxx
    github_token: str = ""                     # ghp_xxx or fine-grained PAT

    # ── CRM / Support ─────────────────────────────────────────────────────────
    hubspot_access_token: str = ""             # pat-na1-xxx
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""
    salesforce_username: str = ""
    salesforce_password: str = ""
    salesforce_security_token: str = ""
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    freshdesk_domain: str = ""                 # yourcompany.freshdesk.com
    freshdesk_api_key: str = ""
    zendesk_subdomain: str = ""
    zendesk_email: str = ""
    zendesk_api_token: str = ""

    # ── Payments ─────────────────────────────────────────────────────────────
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    stripe_secret_key: str = ""               # sk_live_xxx or sk_test_xxx

    # ── Logistics ────────────────────────────────────────────────────────────
    delhivery_api_token: str = ""
    delhivery_api_url: str = "https://track.delhivery.com"
    shiprocket_email: str = ""
    shiprocket_password: str = ""

    # ── Cloud / Storage ───────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"

    # ── Calendar / Meetings ───────────────────────────────────────────────────
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""

    # ── Social / Marketing ────────────────────────────────────────────────────
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    mailchimp_api_key: str = ""               # key-us21
    mailchimp_server_prefix: str = ""         # us21

    # ── Security ─────────────────────────────────────────────────────────────
    encryption_master_key: str = ""   # 64 hex chars — generate: secrets.token_hex(32)
    jwt_secret: str = "change-me"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
