document.querySelectorAll("[data-transaction-category]").forEach((category) => {
  const select = category.querySelector("select");
  const custom = category.querySelector("[data-custom-category]");
  const input = custom.querySelector("input");
  const customValue = category.dataset.customValue;
  const picker = category.querySelector("details");
  const trigger = picker.querySelector("summary");
  const label = category.querySelector("label");
  const selection = trigger.querySelector("span");
  const options = picker.querySelector("ul");
  const type = document.getElementById(category.dataset.typeId);
  const groups = new Map(
    Array.from(select.querySelectorAll("optgroup"), (group, index) => [
      type.options[index + 1].value, group,
    ]),
  );

  if (!select.value && input.value) select.value = customValue;

  const update = () => {
    const group = groups.get(type.value);
    const matchingOption = Array.from(group?.children || []).find((option) => option.value === select.value);
    if (!group || (!matchingOption && select.value !== customValue)) select.value = "";
    const isCustom = select.value === customValue;
    selection.textContent = group ? (matchingOption || select.selectedOptions[0]).textContent : category.dataset.selectType;
    custom.hidden = !isCustom;
    input.disabled = !isCustom;
    input.required = isCustom;
    for (const item of options.children) {
      item.hidden = !group || (item.option.parentElement !== group && item.option.value !== customValue);
      const button = item.firstElementChild;
      button.setAttribute("aria-pressed", String(button.value === select.value));
    }
  };

  for (const option of Array.from(select.options).slice(1)) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.value = option.value;
    button.textContent = option.textContent;
    item.option = option;
    item.append(button);
    options.append(item);
    button.addEventListener("click", () => {
      option.selected = true;
      picker.open = false;
      update();
      (custom.hidden ? trigger : input).focus();
    });
  }
  type.addEventListener("change", () => {
    picker.open = false;
    select.value = "";
    input.value = "";
    update();
  });
  trigger.addEventListener("click", (event) => {
    if (!type.value) {
      event.preventDefault();
      type.focus();
    }
  });
  picker.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && picker.open) {
      event.preventDefault();
      picker.open = false;
      trigger.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!picker.contains(event.target)) picker.open = false;
  });
  label.removeAttribute("for");
  label.addEventListener("click", () => trigger.focus());
  select.hidden = true;
  picker.hidden = false;
  update();
});
