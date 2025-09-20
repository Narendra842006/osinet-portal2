# OSINT Portal Deployment Guide

## 1. Heroku Deployment (Recommended)

### Prerequisites:
- Install [Git](https://git-scm.com/)
- Install [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
- Create a [Heroku account](https://signup.heroku.com/)

### Steps:

1. **Login to Heroku:**
   ```bash
   heroku login
   ```

2. **Initialize Git repository (if not already done):**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

3. **Create Heroku app:**
   ```bash
   heroku create your-osint-portal-name
   ```

4. **Deploy to Heroku:**
   ```bash
   git push heroku main
   ```

5. **Open your app:**
   ```bash
   heroku open
   ```

### Environment Variables (if needed):
```bash
heroku config:set FLASK_DEBUG=False
heroku config:set SECRET_KEY=your-secret-key-here
```

---

## 2. Railway Deployment

### Steps:

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login and deploy:**
   ```bash
   railway login
   railway init
   railway up
   ```

---

## 3. Render Deployment

### Steps:

1. Push your code to GitHub
2. Go to [Render.com](https://render.com/)
3. Create a new Web Service
4. Connect your GitHub repository
5. Use these settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Python Version:** 3.10.11

---

## 4. DigitalOcean App Platform

### Steps:

1. Push code to GitHub
2. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
3. Create new app from GitHub repository
4. Configure:
   - **Run Command:** `gunicorn app:app`
   - **HTTP Port:** 8080

---

## 5. AWS EC2 Deployment

### Steps:

1. **Launch EC2 instance** (Ubuntu 20.04 LTS)

2. **Connect to instance and setup:**
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip nginx git -y
   
   # Clone your repository
   git clone https://github.com/your-username/osinet-portal.git
   cd osinet-portal
   
   # Install dependencies
   pip3 install -r requirements.txt
   
   # Install and configure Gunicorn
   pip3 install gunicorn
   
   # Run with Gunicorn
   gunicorn --bind 0.0.0.0:8000 app:app
   ```

3. **Configure Nginx (optional):**
   ```bash
   sudo nano /etc/nginx/sites-available/osint-portal
   ```
   
   Add:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

---

## 6. Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

### Build and run:
```bash
docker build -t osint-portal .
docker run -p 5000:5000 osint-portal
```

---

## 7. VPS Deployment (Ubuntu/CentOS)

### Ubuntu/Debian:
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install python3 python3-pip python3-venv nginx git -y

# Clone repository
git clone https://github.com/your-username/osinet-portal.git
cd osinet-portal

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install process manager
pip install supervisor

# Run with Gunicorn
gunicorn --bind 0.0.0.0:8000 --workers 3 app:app
```

---

## Important Notes:

### Security Considerations:
- Set `FLASK_DEBUG=False` in production
- Use strong SECRET_KEY
- Configure proper firewall rules
- Use HTTPS in production
- Sanitize user inputs
- Rate limiting for API endpoints

### Database:
- Current setup uses SQLite (file-based)
- For production, consider PostgreSQL or MySQL
- Backup database regularly

### Monitoring:
- Set up logging
- Monitor application performance
- Set up alerts for downtime

### Environment Variables:
```bash
export FLASK_DEBUG=False
export SECRET_KEY=your-very-secret-key
export DATABASE_URL=sqlite:///history.db
```

---

## Quick Heroku Deployment Commands:

```bash
# 1. Prepare files (already done)
# 2. Git setup
git add .
git commit -m "Ready for deployment"

# 3. Heroku setup
heroku create your-app-name
git push heroku main

# 4. Open app
heroku open
```

Your app will be available at: `https://your-app-name.herokuapp.com`
