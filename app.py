import streamlit as st
from pathlib import Path
import os
import urllib.parse
from dotenv import load_dotenv

from sqlalchemy import create_engine
import sqlite3
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit, create_sql_agent
from langchain_community.callbacks import StreamlitCallbackHandler
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_groq import ChatGroq

# ---------------------------------------------------------
# Helper to read secrets from Streamlit Secrets or .env
# ---------------------------------------------------------
# Load local .env if present
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()


def get_secret(key: str, default: str = "") -> str:
    """Retrieve secret from st.secrets, environment variable, or fallback default."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


st.set_page_config(page_title="LangChain: Chat with SQL DB", page_icon="🦜", layout="wide")
st.title("🦜 LangChain: Chat with SQL DB")

LOCALDB = "USE_LOCALDB"
MYSQL = "USE_MYSQL"
MSSQL = "USE_MSSQL"

# Database options: Defaulting to SQLite ensures the demo works out-of-the-box
radio_opt = [
    "Use SQLite 3 Database - Student.db",
    "Connect to ERP Database (SQL Server)",
    "Connect to MySQL Database"
]

selected_opt = st.sidebar.radio(label="Choose the DB which you want to chat", options=radio_opt, index=0)

# Sidebar configurations per DB type
table_filter = None
default_mssql_conn = get_secret("MSSQL_CONN_STRING", "")

if selected_opt == radio_opt[1]:
    db_uri = MSSQL
    st.sidebar.subheader("ERP SQL Server Details")
    mssql_conn_input = st.sidebar.text_area(
        "Connection String",
        value=default_mssql_conn,
        height=120,
        placeholder="Server=your-server.database.windows.net;Database=your_db;User Id=your_user;Password=your_pass;Encrypt=True;TrustServerCertificate=True;",
        help="ADO.NET / ODBC style connection string (can also be configured via MSSQL_CONN_STRING secret)"
    )
    table_filter_input = st.sidebar.text_input(
        "Focus on specific tables (optional)",
        value="",
        placeholder="e.g. Customers, Warehouses, Purchases",
        help="Specifying tables speeds up initial schema inspection significantly for large databases."
    )
    if table_filter_input.strip():
        table_filter = [t.strip() for t in table_filter_input.split(",") if t.strip()]

    if not mssql_conn_input.strip():
        st.warning("⚠️ Please provide a SQL Server connection string in the sidebar (or configure MSSQL_CONN_STRING in Streamlit secrets) to connect.")
        st.stop()

elif selected_opt == radio_opt[2]:
    db_uri = MYSQL
    st.sidebar.subheader("MySQL Details")
    mysql_host = st.sidebar.text_input("MySQL Host", value=get_secret("MYSQL_HOST", "localhost"))
    mysql_user = st.sidebar.text_input("MySQL User", value=get_secret("MYSQL_USER", "root"))
    mysql_password = st.sidebar.text_input("MySQL Password", type="password", value=get_secret("MYSQL_PASSWORD", ""))
    mysql_db = st.sidebar.text_input("MySQL Database", value=get_secret("MYSQL_DB", ""))

else:
    db_uri = LOCALDB
    st.sidebar.info("Using local SQLite database: student.db")

# LLM Configurations
st.sidebar.subheader("LLM Configuration")
default_api_key = get_secret("GROQ_API_KEY", "")
api_key = st.sidebar.text_input(label="Groq API Key", type="password", value=default_api_key)

available_models = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b"
]
selected_model = st.sidebar.selectbox("Choose Groq Model", options=available_models, index=0)

if not api_key:
    st.warning("⚠️ Please provide a Groq API Key in the sidebar (or configure GROQ_API_KEY in Streamlit secrets) to continue.")
    st.stop()


def get_default_odbc_driver() -> str:
    """Auto-detect available ODBC SQL Server driver."""
    try:
        import pyodbc
        installed = pyodbc.drivers()
        for driver_name in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "FreeTDS", "SQL Server"]:
            if driver_name in installed:
                return driver_name
    except Exception:
        pass
    return "ODBC Driver 17 for SQL Server"


def build_mssql_engine_url(conn_str: str) -> str:
    """Parse connection string into a SQLAlchemy pymssql or pyodbc URL."""
    params = {}
    for part in conn_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.strip().lower()] = v.strip()

    server = params.get("server", "")
    database = params.get("database", "")
    user = params.get("user id", params.get("uid", ""))
    pwd = params.get("password", params.get("pwd", ""))

    # Prefer pymssql (works natively on Linux/Streamlit Cloud without requiring system-level ODBC drivers)
    try:
        import pymssql
        u = urllib.parse.quote_plus(user)
        p = urllib.parse.quote_plus(pwd)
        s = server.split(",")[0].strip()
        port = ""
        if "," in server:
            _, port_val = server.split(",", 1)
            port = f":{port_val.strip()}"
        return f"mssql+pymssql://{u}:{p}@{s}{port}/{database}?charset=utf8"
    except ImportError:
        pass

    # Fallback to pyodbc
    encrypt = "yes" if params.get("encrypt", "").lower() in ["true", "yes"] else "no"
    trust_cert = "yes" if params.get("trustservercertificate", "").lower() in ["true", "yes"] else "no"
    driver = params.get("driver", get_default_odbc_driver())

    odbc_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={pwd};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
    )
    return f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}"


@st.cache_resource(ttl="2h")
def configure_db(db_type, mssql_conn=None, selected_tables=None, mysql_host=None, mysql_user=None, mysql_password=None, mysql_db=None):
    if db_type == LOCALDB:
        dbfilepath = (Path(__file__).parent / "student.db").absolute()
        creator = lambda: sqlite3.connect(f"file:{dbfilepath}?mode=ro", uri=True)
        return SQLDatabase(create_engine("sqlite:///", creator=creator), sample_rows_in_table_info=0)

    elif db_type == MYSQL:
        if not (mysql_host and mysql_user and mysql_password and mysql_db):
            st.error("Please provide all MySQL connection details.")
            st.stop()
        return SQLDatabase(
            create_engine(f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_db}"),
            sample_rows_in_table_info=0
        )

    elif db_type == MSSQL:
        if not mssql_conn:
            st.error("Please provide the SQL Server connection string.")
            st.stop()
        engine_url = build_mssql_engine_url(mssql_conn)
        engine = create_engine(engine_url)
        tables_arg = tuple(selected_tables) if selected_tables else None
        return SQLDatabase(engine, include_tables=tables_arg, sample_rows_in_table_info=0)


with st.spinner("Connecting to database and inspecting schema..."):
    try:
        if db_uri == MSSQL:
            db = configure_db(db_uri, mssql_conn=mssql_conn_input, selected_tables=table_filter)
        elif db_uri == MYSQL:
            db = configure_db(db_uri, mysql_host=mysql_host, mysql_user=mysql_user, mysql_password=mysql_password, mysql_db=mysql_db)
        else:
            db = configure_db(db_uri)
        st.sidebar.success(f" Connected! {len(db.get_usable_table_names())} table(s) loaded.")
    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.stop()

# LLM Model setup
llm = ChatGroq(groq_api_key=api_key, model_name=selected_model, streaming=True, temperature=0)

# Toolkit & Agent with Conversational Memory Prompt
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

custom_prefix = (
    "You are an agent designed to interact with a SQL database.\n"
    "Given an input question and the previous conversation history, determine what information the user needs.\n"
    "If the user refers to previous queries, tables, entities, or results (such as 'same query again', 'repeat that query', 'show more details', 'what about that customer'), "
    "use the conversation history to understand their intent and run the appropriate query.\n"
    "Create a syntactically correct {dialect} query, run it, and answer clearly.\n"
    "Unless the user specifies a specific number of examples, limit your query to at most {top_k} results.\n"
    "DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.)."
)

prompt = ChatPromptTemplate.from_messages([
    ("system", custom_prefix.format(dialect=db.dialect, top_k=10)),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    prompt=prompt,
    verbose=True,
    agent_type="tool-calling"
)

# Chat messages setup
if "messages" not in st.session_state or st.sidebar.button("Clear message history"):
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you query your database?"}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

user_query = st.chat_input(placeholder="Ask anything from the database...")

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    st.chat_message("user").write(user_query)

    # Build conversation history for the agent from session state
    chat_history = []
    for msg in st.session_state.messages[:-1]:  # exclude the current query just appended
        if msg["role"] == "user":
            chat_history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant" and msg["content"] != "How can I help you query your database?":
            chat_history.append(AIMessage(content=msg["content"]))

    # Keep the last 16 turns to avoid exceeding context window
    chat_history = chat_history[-16:]

    with st.chat_message("assistant"):
        st_callback = StreamlitCallbackHandler(st.container())
        try:
            res = agent.invoke(
                {"input": user_query, "chat_history": chat_history},
                {"callbacks": [st_callback]}
            )
            response_text = res.get("output", "") if isinstance(res, dict) else str(res)
        except Exception as e:
            response_text = f"An error occurred while executing the query: {e}"

        st.session_state.messages.append({"role": "assistant", "content": response_text})
        st.write(response_text)
