import { OutputBlock } from './ui/OutputBlock'

interface ExplanationPanelProps {
  text: string
}

export function ExplanationPanel({ text }: ExplanationPanelProps) {
  return (
    <OutputBlock label="explanation" accent="var(--color-accent)">
      <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--color-text)', lineHeight: 1.7, fontFamily: 'var(--font-ui)' }}>
        {text}
      </p>
    </OutputBlock>
  )
}
