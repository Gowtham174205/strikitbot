Write-Host "Pushing latest changes to GitHub..." -ForegroundColor Green
git push origin main

Write-Host "Connecting to AWS EC2 and deploying..." -ForegroundColor Green
ssh -i "C:\Users\Gowtham P\Downloads\strikit-key.pem" -o StrictHostKeyChecking=no ubuntu@bot.strikit.in "cd ~/strikitbot && git pull origin main && pm2 restart strikit-bot"

Write-Host "Deployment Complete!" -ForegroundColor Green
