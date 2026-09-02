import React from 'react';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

export default function AgentActivityTracker({ activeStep = 1 }) {
  const steps = [
    { id: 1, label: 'Product Searched' },
    { id: 2, label: 'Product Selected' },
    { id: 3, label: 'Stock Verified' },
    { id: 4, label: 'Order Created' },
    { id: 5, label: 'Payment Verified' },
  ];

  return (
    <div className="agent-activity-bar">
      <div className="activity-label">Agent Action Status:</div>
      <div className="activity-steps">
        {steps.map((step) => {
          const isDone = activeStep > step.id;
          const isCurrent = activeStep === step.id;

          return (
            <div
              key={step.id}
              className={`step-pill ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`}
            >
              {isDone ? (
                <CheckCircle2 size={13} color="var(--accent-success)" />
              ) : isCurrent ? (
                <Loader2 size={13} className="spin-icon" color="var(--accent-primary)" />
              ) : (
                <Circle size={12} color="var(--text-dim)" />
              )}
              <span>{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
