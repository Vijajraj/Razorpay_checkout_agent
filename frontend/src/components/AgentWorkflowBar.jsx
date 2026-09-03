import React from 'react';
import { Check, Circle } from 'lucide-react';

export default function AgentWorkflowBar({ activeStep = 1 }) {
  const steps = [
    { id: 1, label: 'Product Searched' },
    { id: 2, label: 'Product Selected' },
    { id: 3, label: 'Stock Verified' },
    { id: 4, label: 'Order Created' },
    { id: 5, label: 'Payment Verified' },
  ];

  return (
    <div className="compact-workflow-bar">
      {steps.map((step, idx) => {
        const isDone = activeStep > step.id;
        const isCurrent = activeStep === step.id;

        return (
          <React.Fragment key={step.id}>
            <div className={`workflow-step ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`}>
              {isDone ? (
                <Check size={12} strokeWidth={3} className="step-icon done" />
              ) : isCurrent ? (
                <span className="step-dot current" />
              ) : (
                <Circle size={8} className="step-icon muted" />
              )}
              <span className="step-label">{step.label}</span>
            </div>
            {idx < steps.length - 1 && <span className="workflow-arrow">→</span>}
          </React.Fragment>
        );
      })}
    </div>
  );
}
