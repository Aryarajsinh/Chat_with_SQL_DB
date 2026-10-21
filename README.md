# 🦜 LangChain: Chat with SQL DB

An AI-powered conversational agent that enables natural language querying against SQL databases (SQLite, Microsoft SQL Server / ERP, and MySQL) using LangChain and Groq LLMs.

---

## 🌟 Features

- **Multi-Database Support**:
  - **SQLite** (includes pre-configured `student.db` for instant out-of-the-box demo).
  - **Microsoft SQL Server / ERP** (supports remote connection strings with ODBC Driver 17/18 & FreeTDS).
  - **MySQL** (host, user, password, and database).
- **Fast Schema Inspection**: Configured with `sample_rows_in_table_info=0` and optional table focusing for rapid schema loading over cloud networks.
- **Conversational Memory**: Remembers context across turns for follow-up questions.
- **Security-First Architecture**: Built to safely deploy to Streamlit Cloud using `st.secrets` or local `.env`—no hardcoded passwords or API keys.

---

## 🚀 Quickstart (Local)

### 1. Clone the repository
```bash
git clone https://github.com/Aryarajsinh/Chat_with_SQL_DB.git
cd Chat_with_SQL_DB
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment variables (optional)
Create a `.env` file in the root folder (it is automatically ignored by `.gitignore`):
```env
# Required for Groq models
GROQ_API_KEY=gsk_your_groq_api_key_here

# Optional: Default SQL Server / ERP connection string
MSSQL_CONN_STRING=Server=your-server.database.windows.net;Database=your_db;User Id=your_user;Password=your_password;Encrypt=True;TrustServerCertificate=True;

# Optional: Default MySQL settings
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=your_db_name
```

*(You can also simply enter your API key and connection strings directly into the Streamlit sidebar at runtime).*

### 4. Run the application
```bash
streamlit run app.py
```

---

## ☁️ Deployment on Streamlit Cloud

To deploy this project to [Streamlit Community Cloud](https://share.streamlit.io):

1. Push your repository to GitHub.
2. Sign in to **Streamlit Community Cloud** and click **New App**.
3. Select your repository: `Aryarajsinh/Chat_with_SQL_DB`, branch `main`, and main file `app.py`.
4. Click **Advanced Settings** -> **Secrets**.
5. Paste your private credentials into the Secrets box:
   ```toml
   GROQ_API_KEY = "gsk_your_actual_groq_api_key"
   MSSQL_CONN_STRING = "Server=your-server.database.windows.net;Database=your_db;User Id=your_user;Password=your_password;Encrypt=True;TrustServerCertificate=True;MultipleActiveResultSets=True;"
   ```
6. Click **Deploy**!

Streamlit Cloud will securely inject these secrets into your application without ever exposing them to GitHub.

---

## 🔒 Security Best Practices

- `.env` and `.streamlit/secrets.toml` are listed in `.gitignore` and are **never** committed to version control.
- SQL DML statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`) are forbidden in the agent prompt.

