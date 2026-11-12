for (const button of document.querySelectorAll(".password-toggle")) {
  const input = document.getElementById(button.getAttribute("aria-controls"));
  button.addEventListener("click", () => {
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    button.setAttribute("aria-pressed", String(showPassword));
  });
}
