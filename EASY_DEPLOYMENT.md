# 🚀 Easy Deployment Options for OSINT Portal

## ✅ SOLUTION: Skip Heroku - Use These FREE Alternatives

Since Heroku requires payment verification, here are better free options:

## 🔥 1. Railway (Recommended - No Payment Required)

### Super Simple Steps:
1. **Go to:** [railway.app](https://railway.app/)
2. **Sign up** with GitHub
3. **Click:** "New Project" → "Deploy from GitHub repo"
4. **Select:** your `osinet-portal` repository
5. **Deploy:** Railway auto-detects Flask and deploys!

**Your app will be live at:** `https://your-project.railway.app`

---

## 🌐 2. Render.com (Also Free)

### Steps:
1. **Go to:** [render.com](https://render.com/)
2. **Connect** GitHub account
3. **Create** new Web Service
4. **Select** your repository
5. **Settings:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

---

## ⚡ 3. Vercel (Serverless)

### Steps:
1. **Go to:** [vercel.com](https://vercel.com/)
2. **Import** from GitHub
3. **Deploy** automatically

---

## 🐳 4. Local Docker (Test Before Deployment)

### Run locally with Docker:
```bash
# Build image
docker build -t osint-portal .

# Run container
docker run -p 5000:5000 osint-portal
```

Access at: `http://localhost:5000`

---

## 📋 Git Commands (Run from project directory)

```bash
# Navigate to project directory first
cd "C:\Users\anisha\OneDrive\Desktop\OSINT-Portal\osinet-portal"

# Check status
git status

# Add all files
git add .

# Commit changes
git commit -m "Ready for deployment"

# Push to GitHub
git push origin main
```

---

## 🎯 Recommended Approach:

1. **Push code to GitHub** (your repo is already set up)
2. **Use Railway.app** - easiest and fastest
3. **No payment required**
4. **Automatic deployments**

**Your files are ready!** All deployment configurations are already created.

## 🛠️ Already Created Files:
- ✅ `Procfile`
- ✅ `requirements.txt` (updated)
- ✅ `runtime.txt`
- ✅ `Dockerfile`
- ✅ Production-ready `app.py`

**Next Step:** Choose Railway or Render and deploy in 2 minutes!
