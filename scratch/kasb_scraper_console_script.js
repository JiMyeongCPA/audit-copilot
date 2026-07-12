(async function () {
  const TARGET_STANDARDS = ["240", "315", "330", "500", "520", "540", "570"];
  const STOP_AFTER = "570";
  const MAX_STEPS = 2000;

  const collected = {};
  const seen = new Set();

  function currentStandardNumber() {
    return window.location.pathname.split("/")[2];
  }

  function captureParas(standard) {
    if (!collected[standard]) collected[standard] = [];
    document.querySelectorAll(".para").forEach((el) => {
      const text = el.innerText.trim();
      const key = standard + "::" + text;
      if (text && !seen.has(key)) {
        seen.add(key);
        collected[standard].push(text);
      }
    });
  }

  function findNextLink() {
    const links = Array.from(document.querySelectorAll('footer a[href^="/s/"]'));
    return links.find((a) => {
      const icon = a.querySelector("i.material-icons");
      return icon && icon.textContent.trim() === "chevron_right";
    });
  }

  for (let i = 0; i < MAX_STEPS; i++) {
    const std = currentStandardNumber();
    if (TARGET_STANDARDS.includes(std)) {
      captureParas(std);
    }

    const nextLink = findNextLink();
    if (!nextLink) break;

    const href = nextLink.getAttribute("href");
    const nextStd = href.split("/")[2];

    if (std === STOP_AFTER && nextStd !== STOP_AFTER) break;

    nextLink.click();
    await new Promise((r) => setTimeout(r, 800));
  }

  for (const std of TARGET_STANDARDS) {
    const text = (collected[std] || []).join("\n\n");
    if (!text) continue;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `감사기준서_${std}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    await new Promise((r) => setTimeout(r, 400));
  }

  console.log(
    "완료:",
    Object.keys(collected)
      .map((k) => `${k}(${collected[k].length}문단)`)
      .join(", ")
  );
})();
