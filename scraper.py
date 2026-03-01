name: Global Production API

on:
  schedule:
    - cron: '*/15 * * * *'
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  scrape_and_deploy:
    environment:
      name: github-pages
      # FIX: Changed colon to dot below
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
      
      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4 urllib3

      - name: Run Scraper
        # Ensure your entry file is named main.py
        run: python main.py
      
      - name: Commit and Push Data
        run: |
          git config --global user.name "Views-Bot"
          git config --global user.email "bot@views-project.local"
          git add index.json
          # Only commits if changes exist; skips if no changes found
          git diff --quiet && git diff --staged --quiet || (git commit -m "Live Data Update: $(date)" && git push)
        continue-on-error: true

      - name: Setup Pages
        uses: actions/configure-pages@v5
      
      - name: Upload Pages Artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '.' 
      
      - name: Deploy to GitHub Pages
        id: deployment 
        uses: actions/deploy-pages@v4
