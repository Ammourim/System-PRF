/* Sistema PRF - JavaScript minimo: confirmacoes, selects dependentes e
   cronometro. Nada de framework; a aplicacao funciona sem JS, exceto pelo
   cronometro do simulado. A navegacao e HTML/CSS puro em qualquer tamanho de tela. */

(function () {
  "use strict";

  // Confirmacao em acoes destrutivas ---------------------------------------
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  // Assuntos dependentes da disciplina -------------------------------------
  function loadSubjects(select) {
    var targetId = select.getAttribute("data-subject-target");
    var target = document.getElementById(targetId);
    if (!target) return;
    var disciplineId = select.value;
    if (!disciplineId) {
      target.innerHTML = '<option value="">-</option>';
      return;
    }
    fetch("/disciplinas/api/assuntos?discipline_id=" + encodeURIComponent(disciplineId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var current = target.getAttribute("data-selected") || "";
        var html = '<option value="">- (ou digite abaixo)</option>';
        data.subjects.forEach(function (s) {
          html += '<option value="' + s.id + '"' +
            (String(s.id) === String(current) ? " selected" : "") + ">" +
            s.name.replace(/[<>&]/g, "") + "</option>";
        });
        target.innerHTML = html;
      })
      .catch(function () { /* offline: o campo de texto livre continua valendo */ });
  }

  document.querySelectorAll("[data-subject-target]").forEach(function (select) {
    select.addEventListener("change", function () { loadSubjects(select); });
    if (select.value) loadSubjects(select);
  });

  // Cronometro do simulado --------------------------------------------------
  var timer = document.getElementById("timer");
  if (timer) {
    var display = document.getElementById("timer-display");
    var elapsedOut = document.getElementById("timer-elapsed");
    var answeredInput = document.getElementById("timer-answered");
    var remainingOut = document.getElementById("timer-remaining-questions");
    var minutesInput = document.getElementById("timer-minutes");
    var totalInput = document.getElementById("timer-total");
    var startBtn = document.getElementById("timer-start");
    var pauseBtn = document.getElementById("timer-pause");
    var finishBtn = document.getElementById("timer-finish");
    var state = { running: false, startedAt: null, elapsed: 0, tick: null };

    function pad(n) { return String(n).padStart(2, "0"); }

    function format(seconds) {
      var sign = seconds < 0 ? "-" : "";
      seconds = Math.abs(Math.floor(seconds));
      return sign + pad(Math.floor(seconds / 3600)) + ":" +
        pad(Math.floor((seconds % 3600) / 60)) + ":" + pad(seconds % 60);
    }

    function render() {
      var planned = (parseInt(minutesInput.value, 10) || 0) * 60;
      var elapsed = state.elapsed + (state.running ? (Date.now() - state.startedAt) / 1000 : 0);
      var remaining = planned - elapsed;
      display.textContent = format(remaining);
      display.classList.toggle("over", remaining < 0);
      elapsedOut.textContent = format(elapsed);
      var total = parseInt(totalInput.value, 10) || 0;
      var answered = parseInt(answeredInput.value, 10) || 0;
      remainingOut.textContent = Math.max(total - answered, 0);
      document.getElementById("form-total-minutes").value = Math.round(elapsed / 60);
      document.getElementById("form-time-left").value = Math.max(Math.round(remaining / 60), 0);
      document.getElementById("form-planned-minutes").value = minutesInput.value;
      document.getElementById("form-total").value = totalInput.value;
    }

    function start() {
      if (state.running) return;
      state.running = true;
      state.startedAt = Date.now();
      state.tick = setInterval(render, 250);
      document.body.classList.add("focus-mode");
      startBtn.disabled = true;
      pauseBtn.disabled = false;
    }

    function pause() {
      if (!state.running) return;
      state.elapsed += (Date.now() - state.startedAt) / 1000;
      state.running = false;
      clearInterval(state.tick);
      startBtn.disabled = false;
      pauseBtn.disabled = true;
      render();
    }

    startBtn.addEventListener("click", start);
    pauseBtn.addEventListener("click", pause);
    finishBtn.addEventListener("click", function () {
      pause();
      document.body.classList.remove("focus-mode");
      document.getElementById("timer-result").classList.remove("hidden");
      render();
    });
    [minutesInput, totalInput, answeredInput].forEach(function (input) {
      input.addEventListener("input", render);
    });
    document.querySelectorAll("[data-answered-step]").forEach(function (button) {
      button.addEventListener("click", function () {
        var step = parseInt(button.getAttribute("data-answered-step"), 10);
        answeredInput.value = Math.max((parseInt(answeredInput.value, 10) || 0) + step, 0);
        render();
      });
    });
    render();

    window.addEventListener("beforeunload", function (event) {
      if (state.running) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }
})();
