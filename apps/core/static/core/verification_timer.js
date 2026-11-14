(() => {
  const timer = document.getElementById("verification-timer");
  if (!timer) return;
  const countdown = document.getElementById("verification-countdown");
  const resend = document.getElementById("verification-resend");
  const expiresAt = performance.now() + Number(timer.dataset.remainingMs);

  const updateTimer = () => {
    const remaining = Math.max(0, expiresAt - performance.now());
    const seconds = Math.ceil(remaining / 1000);
    const minutesText = String(Math.floor(seconds / 60)).padStart(2, "0");
    const secondsText = String(seconds % 60).padStart(2, "0");
    countdown.textContent = minutesText + ":" + secondsText;
    if (remaining === 0) {
      window.clearInterval(timerInterval);
      document.getElementById("verification-submit").disabled = true;
      document.getElementById("verification-locked").hidden = true;
      document.getElementById("verification-expired").hidden = false;
      if (resend) resend.disabled = Number(resend.dataset.resendsLeft) <= 0;
    }
  };
  const timerInterval = window.setInterval(updateTimer, 200);
  updateTimer();
  timer.hidden = false;
})();
