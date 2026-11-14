(() => {
  const label = document.getElementById("verification-code-label");
  const codeField = document.getElementById(label.htmlFor);
  const boxes = document.getElementById("verification-code-boxes");
  const digits = Array.from(boxes.querySelectorAll("input"));

  const syncCode = () => {
    codeField.value = digits.map((input) => input.value).join("");
  };

  const fillDigits = (value, index) => {
    const numbers = value.replace(/[^0-9]/g, "").slice(0, digits.length);
    if (!numbers) {
      digits[index].value = "";
      syncCode();
      return;
    }
    const start = numbers.length === digits.length ? 0 : index;
    const end = Math.min(start + numbers.length, digits.length);
    for (let position = start; position < end; position += 1) {
      digits[position].value = numbers[position - start];
    }
    syncCode();
    digits[Math.min(end, digits.length - 1)].focus();
  };

  digits.forEach((input, index) => {
    input.required = true;
    input.addEventListener("focus", () => input.select());
    input.addEventListener("input", (event) => {
      const value = event.inputType === "insertText" && event.data !== null
        ? event.data
        : input.value;
      fillDigits(value, index);
    });
    input.addEventListener("paste", (event) => {
      const value = event.clipboardData.getData("text");
      event.preventDefault();
      fillDigits(value, index);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !input.value && index > 0) {
        event.preventDefault();
        digits[index - 1].value = "";
        digits[index - 1].focus();
        syncCode();
      }
    });
  });

  codeField.removeAttribute("autofocus");
  codeField.type = "hidden";
  label.htmlFor = "";
  const description = codeField.getAttribute("aria-describedby");
  if (description) boxes.setAttribute("aria-describedby", description);
  codeField.value = "";
  boxes.hidden = false;
  if (!description) digits[0].focus();
})();
