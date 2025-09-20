# Railway Deployment Guide for OSINT Portal

## Quick Railway Deployment (Free Alternative to Heroku)

### Method 1: Direct GitHub Deployment (Easiest)

1. **Push your code to GitHub first:**
   - Go to your repository: https://github.com/nani-coder-ship-it/osinet-portal
   - Make sure all files are pushed to the main branch

2. **Deploy on Railway:**
   - Go to [Railway.app](https://railway.app/)
   - Click "Start a New Project"
   - Choose "Deploy from GitHub repo"
   - Select your `osinet-portal` repository
   - Railway will automatically detect it's a Python Flask app
   - Click "Deploy Now"

### Method 2: Railway CLI (Alternative)

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

### Method 3: Direct Upload

1. Go to [Railway.app](https://railway.app/)
2. Click "Start a New Project"
3. Choose "Deploy from template"
4. Select "Python Flask"
5. Upload your project folder

## Configuration for Railway:

Railway will automatically detect your Flask app using these files:
- ✅ `Procfile` (already created)
- ✅ `requirements.txt` (already updated)
- ✅ `runtime.txt` (already created)

## Alternative Free Platforms:

### 1. Render.com
- Go to [Render.com](https://render.com/)
- Connect GitHub repo
- Auto-deploys on git push

### 2. Vercel (Serverless)
- Go to [Vercel.com](https://vercel.com/)
- Import from GitHub
- Zero configuration needed

### 3. Fly.io
- Install flyctl
- Run `fly launch` in project directory

## Quick Steps Summary:

1. **First, push to GitHub** (if not already done)
2. **Go to Railway.app**
3. **Connect GitHub repo**
4. **Deploy automatically**
5. **Your app will be live!**

## Environment Variables (if needed):
- `FLASK_DEBUG=False`
- `PORT=5000` (Railway sets this automatically)

Your app will be accessible at: `https://your-project-name.railway.app`
