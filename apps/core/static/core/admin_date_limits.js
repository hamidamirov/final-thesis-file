(() => {
    const shortcuts = window.DateTimeShortcuts;
    const calendar = window.CalendarNamespace;
    if (!shortcuts || !calendar) {
        return;
    }

    function disableLink(link) {
        const label = document.createElement("span");
        label.className = "calendar-unavailable";
        label.textContent = link.textContent;
        label.setAttribute("aria-disabled", "true");
        link.replaceWith(label);
    }

    const draw = calendar.draw;
    calendar.draw = function (month, year, id, callback, selected) {
        draw.call(this, month, year, id, callback, selected);
        if (!id.startsWith(shortcuts.calendarDivName2)) {
            return;
        }
        const index = id.slice(shortcuts.calendarDivName2.length);
        const latestDate = shortcuts.calendarInputs[index]?.dataset.latestDate;
        if (!latestDate) {
            return;
        }
        const latestDay = Number(latestDate.replaceAll("-", ""));
        const monthStart = year * 10000 + month * 100;
        for (const dayLink of document.getElementById(id).querySelectorAll("td a")) {
            if (monthStart + Number(dayLink.textContent) > latestDay) {
                disableLink(dayLink);
            }
        }
    };

    const addCalendar = shortcuts.addCalendar;
    shortcuts.addCalendar = function (input) {
        const index = this.calendars.length;
        addCalendar.call(this, input);
        if (input.dataset.latestDate) {
            const box = document.getElementById(this.calendarDivName1 + index);
            disableLink(box.querySelector(".calendar-shortcuts a:last-child"));
        }
    };
})();
