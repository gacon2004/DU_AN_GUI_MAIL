from fastapi import FastAPI, BackgroundTasks, Form, Request, Depends, HTTPException, Cookie, Response
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from email.message import EmailMessage
import aiosmtplib
import os
from connect import get_connection
from dotenv import load_dotenv
from auth import decode_token,create_access_token
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config




load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="minh-secret")
templates = Jinja2Templates(directory="templates")

config = Config('.env')
oauth = OAuth(config)
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauthfb =OAuth(config)
oauthfb.register(
    name='facebook',
    client_id=os.getenv("FACEBOOK_CLIENT_ID"),
    client_secret=os.getenv("FACEBOOK_CLIENT_SECRET"),
    access_token_url='https://graph.facebook.com/v10.0/oauth/access_token',
    access_token_params=None,
    authorize_url='https://www.facebook.com/v10.0/dialog/oauth',
    authorize_params=None,
    api_base_url='https://graph.facebook.com/v10.0/',
    client_kwargs={'scope': 'email'},
)

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

def get_current_user_from_cookie(access_token: str = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    try:
        payload = decode_token(access_token)
        return payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Token sai hoặc hết hạn")
    

async def send_email_background(email_to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = EMAIL_USER
    message["To"] = email_to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname="smtp.gmail.com",
        port=587,
        start_tls=True,
        username=EMAIL_USER,
        password=EMAIL_PASS,
    )

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request, message: str = None):
    return templates.TemplateResponse("index.html", {"request": request, "success_message": message})

# @app.post("/send-email/")
# async def send_email_form(
#     email_to: str = Form(...),
#     subject: str = Form(...),
#     body: str = Form(...),
#     background_tasks: BackgroundTasks = BackgroundTasks()
# ):
#     background_tasks.add_task(send_email_background, email_to, subject, body)
#     return {"message": "Email đang được gửi"}


@app.post("/send-email/")
async def send_email_form(
    request: Request,
    email_to: str = Form(...),
    body: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    access_token: str = Cookie(None)
):
    try:
        current_user = get_current_user_from_cookie(access_token)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)
    
    subject = f"{current_user} đã gửi một mail cho bạn"
    background_tasks.add_task(send_email_background, email_to, subject, body)
    return templates.TemplateResponse("index.html", {
    "request": request,
    "success_message": "Gửi email thành công!",
    "error_message": "Email không hợp lệ.",
    "info_message": "Đang xử lý..."
    })

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...)
):
    try:
        # Kiểm tra mật khẩu nhập lại
        if password != confirm_password:
            return templates.TemplateResponse("signup.html", {
                "request": request,
                "message": "Mật khẩu không khớp."
            })

        conn = get_connection()
        cursor = conn.cursor()

        # Kiểm tra username đã tồn tại chưa
        cursor.execute("SELECT username FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            return templates.TemplateResponse("signup.html", {
                "request": request,
                "message": "Tên đăng nhập đã tồn tại."
            })

        # Chèn người dùng mới
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, password, role)
        )
        conn.commit()
        return RedirectResponse(url="/login", status_code=302)

    except Exception as e:
        print("Lỗi đăng ký:", str(e))  # Ghi lỗi ra console
        return templates.TemplateResponse("register.html", {
            "request": request,
            "message": "Có lỗi xảy ra trong quá trình đăng ký."
        })

    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    if result:
        access_token = create_access_token(data={"sub": username})
        response = RedirectResponse(url="/?message=Đăng nhập thành công!", status_code=302)
        response.set_cookie(key="access_token", value=access_token, httponly=True)
        return response
    else:
        return templates.TemplateResponse("login.html", {"request": request, "message": "Sai tài khoản hoặc mật khẩu"})
    
@app.post("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response

@app.get("/login/google")
async def login_google(request: Request):
    redirect_uri = request.url_for('auth_google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)

    # Lấy thông tin user từ Google
    resp = await oauth.google.get('https://www.googleapis.com/oauth2/v3/userinfo', token=token)
    user_info = resp.json()


    email = user_info["email"]
    name = user_info.get("name")
    message = f"Đăng nhập Google thành công! Xin chào {name}"
    # Tùy chọn: Lưu user_info vào session hoặc database

    # Tạo JWT token
    access_token = create_access_token(data={"sub": email})
    response = RedirectResponse(url=f"/?message={message}", status_code=302)
    response.set_cookie("access_token", access_token, httponly=True)
    return response

@app.get("/login/facebook")
async def login_facebook(request: Request):
    redirect_uri = request.url_for("auth_facebook_callback")
    return await oauthfb.facebook.authorize_redirect(request, redirect_uri)

@app.get("/auth/facebook/callback")
async def auth_facebook_callback(request: Request):
    token = await oauthfb.facebook.authorize_access_token(request)
    resp = await oauthfb.facebook.get("me?fields=id,name,email", token=token)
    user_info = resp.json()

    email = user_info.get("email")
    name = user_info.get("name")

    access_token = create_access_token(data={"sub":  name})
    response = RedirectResponse(url=f"/?message=Chào {name}!")
    response.set_cookie("access_token", access_token, httponly=True)
    return response

@app.get("/delete-data", response_class=HTMLResponse)
async def delete_data():
    return """
    <html>
        <head><title>Xóa dữ liệu</title></head>
        <body>
            <h2>Hướng dẫn xóa dữ liệu</h2>
            <p>Nếu bạn muốn xóa dữ liệu của mình khỏi hệ thống, vui lòng liên hệ qua email: support@example.com</p>
        </body>
    </html>
    """