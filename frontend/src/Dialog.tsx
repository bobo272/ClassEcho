import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'

export default function Dialog({ title, closeLabel, onClose, children, className = '' }: {
  title: string; closeLabel: string; onClose: () => void; children: ReactNode; className?: string
}) {
  const id = useId()
  const container = useRef<HTMLElement>(null)
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousOverflow = document.body.style.overflow
    const element = container.current!
    const focusable = () => Array.from(element.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]')).filter(item => !item.closest('[hidden]') && item.getAttribute('type') !== 'hidden')
    const firstInput = element.querySelector<HTMLElement>('input:not(:disabled):not([type="hidden"]), textarea:not(:disabled)')
    ;(firstInput ?? focusable()[0] ?? element).focus()
    document.body.style.overflow = 'hidden'

    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); return }
      if (event.key !== 'Tab') return
      const items = focusable()
      const first = items[0], last = items[items.length - 1]
      if (!first) { event.preventDefault(); element.focus(); return }
      if (event.shiftKey && (document.activeElement === first || !element.contains(document.activeElement))) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !element.contains(document.activeElement))) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      document.body.style.overflow = previousOverflow
      if (previous?.isConnected) previous.focus()
    }
  }, [])

  return <div className="modal-backdrop"><section ref={container} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1} className={`modal ${className}`}>
    <div className="modal-title"><h2 id={id}>{title}</h2><button className="icon-button" aria-label={closeLabel} onClick={onClose}><X size={18} /></button></div>
    <div className="dialog-content">{children}</div>
  </section></div>
}
