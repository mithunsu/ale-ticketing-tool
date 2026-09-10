# Backend (Flask)

## Local startup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

## Run tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## Browser authentication flow

The frontend must first call `GET http://localhost:5000/api/auth/csrf` and retain the returned `data.csrf_token`. Send that value in the `X-CSRF-Token` header with login and every later `POST`, `PUT`, `PATCH`, or `DELETE` request, together with credentials. `GET`, `HEAD`, and `OPTIONS` requests do not require CSRF validation.

Successful login clears the pre-login session while establishing the authenticated session, so fetch a fresh CSRF token after login for subsequent mutations. Successful password change clears the session and forces login again; fetch a fresh token before that login. CSRF tokens are held in the Flask session and are never stored in PostgreSQL.
