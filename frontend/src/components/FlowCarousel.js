import React, { useRef, useEffect, useState, memo } from 'react';

/**
 * FlowCarousel - A swipeable carousel container optimized for mobile.
 * On desktop, renders children normally. On mobile, enables horizontal
 * snap-scrolling with swipe gestures.
 *
 * Props:
 *   children: React components to display as carousel cards
 *   cardMinWidth: minimum width in px for each card (default 280)
 */
function FlowCarousel({ children, cardMinWidth = 280 }) {
  const containerRef = useRef(null);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  if (!isMobile) {
    // Desktop: render normally
    return <>{children}</>;
  }

  // Mobile: swipeable snap-scroll
  return (
    <div
      ref={containerRef}
      className="flow-carousel"
      role="region"
      aria-label="Swipeable content"
    >
      {React.Children.map(children, (child, i) => (
        <div
          key={i}
          style={{
            flex: `0 0 ${Math.max(cardMinWidth, window.innerWidth * 0.85)}px`,
            maxWidth: window.innerWidth - 32,
          }}
        >
          {child}
        </div>
      ))}
    </div>
  );
}

export default memo(FlowCarousel);
