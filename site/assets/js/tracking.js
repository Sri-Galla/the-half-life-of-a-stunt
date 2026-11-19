// Add real portfolio interactions during instrumentation.
(() => {
  window.dataLayer = window.dataLayer || [];

  // Track explicitly labelled links.
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-track-event]");
    if (!link) return;

    const eventName = link.dataset.trackEvent;
    if (!["repo_open", "dashboard_open"].includes(eventName)) return;

    window.dataLayer.push({
      event: eventName
    });
  });

  // Track scroll milestones once each per page load.
  const reached = new Set();

  function checkScrollDepth() {
    const page = document.documentElement;
    const scrollableHeight = page.scrollHeight - window.innerHeight;

    // Do not count a short, non-scrollable page as a completed read.
    if (scrollableHeight <= 0) return;

    const percent = Math.min(
      100,
      Math.floor((window.scrollY / scrollableHeight) * 100)
    );

    [50, 90].forEach((threshold) => {
      if (percent >= threshold && !reached.has(threshold)) {
        reached.add(threshold);

        window.dataLayer.push({
          event: "scroll_depth",
          percent_scrolled: threshold
        });
      }
    });
  }

  window.addEventListener("scroll", checkScrollDepth, {
    passive: true
  });
})();