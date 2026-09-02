import React from 'react';
import { Check, Circle } from 'lucide-react';

export default function AgentWorkflowBar({ activeStep = 1 }) {
  const steps = [
    { id: 1, label: 'SEARCH' },
    { id: 2, label: 'SELECT' },
    { id: 3, label: 'VERIFY' },
    { id: 4, label: 'ORDER' },
    { id: 5, label: 'PAY' },
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
