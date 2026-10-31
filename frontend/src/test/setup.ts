import "@testing-library/jest-dom";

// Shims for JSDOM environment
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }

  if (!window.ResizeObserver) {
    window.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }

  // TanStack Virtual requires non-zero client dimensions
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 600,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 600,
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    value: 1000,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 1000,
  });

  HTMLElement.prototype.getBoundingClientRect = function () {
    return {
      width: 1000,
      height: 600,
      top: 0,
      left: 0,
      bottom: 600,
      right: 1000,
      x: 0,
      y: 0,
      toJSON: () => {},
    };
  };

  if (typeof HTMLCanvasElement !== "undefined") {
    HTMLCanvasElement.prototype.getContext = ((() => {
      return {
        clearRect: () => {},
        fillRect: () => {},
        beginPath: () => {},
        moveTo: () => {},
        lineTo: () => {},
        stroke: () => {},
        fill: () => {},
        clip: () => {},
        arc: () => {},
        arcTo: () => {},
        rect: () => {},
        closePath: () => {},
        save: () => {},
        restore: () => {},
        translate: () => {},
        scale: () => {},
        rotate: () => {},
        measureText: () => ({ width: 50 }),
        strokeText: () => {},
        fillText: () => {},
        setLineDash: () => {},
        getLineDash: () => [],
        createLinearGradient: () => ({ addColorStop: () => {} }),
        createPattern: () => null,
        drawImage: () => {},
        isPointInPath: () => false,
      };
    }) as unknown as typeof HTMLCanvasElement.prototype.getContext);
  }

  if (typeof (globalThis as { Path2D?: unknown }).Path2D === "undefined") {
    (globalThis as { Path2D?: unknown }).Path2D = class Path2D {
      addPath() {}
      closePath() {}
      moveTo() {}
      lineTo() {}
      bezierCurveTo() {}
      quadraticCurveTo() {}
      arc() {}
      arcTo() {}
      ellipse() {}
      rect() {}
    };
  }
}
