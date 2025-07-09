# Trading Dashboard App

A modular Streamlit-based trading dashboard for managing trades, positions, Dollar Cost Averaging (DCA), and portfolio analytics with PostgreSQL backend.

## Features

- Modular codebase (UI, DB, utils, indicators)
- Streamlit UI for trades, positions, DCA, options, and dashboard
- PostgreSQL integration (configurable via `.streamlit/secrets.toml`)
- Streamlit Cloud ready (secrets, caching)
- Data caching for performance
- Basic authentication support

## Setup

1. **Clone the repo**  
   `git clone <repo-url> && cd trading`

2. **Install dependencies**  
   ```
   pip install -r requirements.txt
   ```

3. **Configure database**  
   Add `.streamlit/secrets.toml`:
   ```
   [postgresql]
   host = "your-db-host"
   port = "your-db-port"
   dbname = "your-db-name"
   user = "your-db-user"
   password = "your-db-password"
   ```

4. **Run locally**  
   ```
   streamlit run app.py
   ```

5. **Authentication**

This app supports basic authentication for user access control.  
You can configure usernames and passwords directly in your code or via environment variables.

- See the relevant section in `app.py` for how to enable and configure basic authentication.

## Deployment

- Deploy to [Streamlit Cloud](https://streamlit.io/cloud)
- Secrets managed via `.streamlit/secrets.toml`
- Add requirements.txt for dependencies

## Directory Structure

```
.
├── app.py
├── db/
├── ui/
├── utils/
├── indicators/
├── config/
├── .streamlit/
├── requirements.txt
├── README.md
└── .gitignore
```

## Notes

- Caching is enabled for DB queries; cache is cleared on data changes.
- For authentication, see the code in `app.py` for basic authentication usage.
- For production, secure your secrets and database access.

## Disclaimer

Most of the code in this repository was generated or written with the assistance of AI (GitHub Copilot, ChatGPT, or similar tools). Please review and test thoroughly before using in production.

![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/venkatgankidi/trade-tracker?utm_source=oss&utm_medium=github&utm_campaign=venkatgankidi%2Ftrade-tracker&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)
