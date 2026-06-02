import React from "react";
import FloatingWidget from "./components/FloatingWidget";

const App: React.FC = () => {
  return (
    <div className="w-screen h-screen bg-transparent overflow-hidden">
      <FloatingWidget />
    </div>
  );
};

export default App;
