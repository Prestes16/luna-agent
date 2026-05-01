import React, { useState } from 'react'
import { ChevronRight, Check } from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

interface FormOption {
  value: string
  label: string
  desc?: string
}

interface FormField {
  id: string
  type: 'radio' | 'checkboxes' | 'text' | 'textarea'
  label: string
  options?: FormOption[]
  placeholder?: string
  default?: string
  required?: boolean
}

export interface LunaFormSchema {
  title: string
  fields: FormField[]
}

interface Props {
  schema: LunaFormSchema
  onSubmit: (text: string) => void
  submitted?: boolean
}

// ── Sub-components ───────────────────────────────────────────────────────────

const RadioField: React.FC<{
  field: FormField
  value: string
  onChange: (v: string) => void
}> = ({ field, value, onChange }) => (
  <div className="space-y-1.5">
    {field.options?.map((opt) => {
      const selected = value === opt.value
      return (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className="w-full flex items-start gap-2.5 p-2.5 rounded-lg text-left transition-all duration-150"
          style={{
            background: selected ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.02)',
            border: `1px solid ${selected ? 'rgba(0,212,255,0.4)' : 'rgba(255,255,255,0.07)'}`,
          }}
        >
          {/* Custom radio circle */}
          <div
            className="flex-shrink-0 mt-0.5 w-4 h-4 rounded-full flex items-center justify-center transition-all"
            style={{
              border: `1.5px solid ${selected ? '#00d4ff' : 'rgba(255,255,255,0.2)'}`,
              background: selected ? 'rgba(0,212,255,0.15)' : 'transparent',
            }}
          >
            {selected && <div className="w-1.5 h-1.5 rounded-full bg-cyber-cyan" />}
          </div>
          <div>
            <p className="text-[12px] font-medium text-cyber-text leading-tight">{opt.label}</p>
            {opt.desc && (
              <p className="text-[11px] text-cyber-muted mt-0.5 leading-tight">{opt.desc}</p>
            )}
          </div>
        </button>
      )
    })}
  </div>
)

const CheckboxesField: React.FC<{
  field: FormField
  values: string[]
  onChange: (v: string[]) => void
}> = ({ field, values, onChange }) => {
  const toggle = (v: string) =>
    values.includes(v) ? onChange(values.filter((x) => x !== v)) : onChange([...values, v])

  return (
    <div className="space-y-1.5">
      {field.options?.map((opt) => {
        const checked = values.includes(opt.value)
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => toggle(opt.value)}
            className="w-full flex items-center gap-2.5 p-2.5 rounded-lg text-left transition-all duration-150"
            style={{
              background: checked ? 'rgba(124,58,237,0.08)' : 'rgba(255,255,255,0.02)',
              border: `1px solid ${checked ? 'rgba(124,58,237,0.4)' : 'rgba(255,255,255,0.07)'}`,
            }}
          >
            <div
              className="flex-shrink-0 w-4 h-4 rounded flex items-center justify-center transition-all"
              style={{
                background: checked ? 'rgba(124,58,237,0.3)' : 'transparent',
                border: `1.5px solid ${checked ? '#7c3aed' : 'rgba(255,255,255,0.2)'}`,
              }}
            >
              {checked && <Check size={10} className="text-cyber-purple" />}
            </div>
            <p className="text-[12px] text-cyber-text leading-tight">{opt.label}</p>
          </button>
        )
      })}
    </div>
  )
}

// ── Main Form ────────────────────────────────────────────────────────────────

export const LunaRequirementsForm: React.FC<Props> = ({ schema, onSubmit, submitted }) => {
  // Initialize state for all fields
  const initialValues: Record<string, string | string[]> = {}
  schema.fields.forEach((f) => {
    if (f.type === 'checkboxes') initialValues[f.id] = []
    else initialValues[f.id] = f.default ?? ''
  })

  const [values, setValues]     = useState<Record<string, string | string[]>>(initialValues)
  const [done, setDone]         = useState(submitted ?? false)

  const setValue = (id: string, v: string | string[]) =>
    setValues((prev) => ({ ...prev, [id]: v }))

  const handleSubmit = () => {
    // Build a natural-language summary to send as user message
    const lines: string[] = []

    schema.fields.forEach((field) => {
      const val = values[field.id]
      if (!val || (Array.isArray(val) && val.length === 0)) return

      if (field.type === 'radio') {
        const opt = field.options?.find((o) => o.value === val)
        lines.push(`**${field.label}:** ${opt?.label ?? val}`)
      } else if (field.type === 'checkboxes') {
        const arr = val as string[]
        const labels = arr.map((v) => field.options?.find((o) => o.value === v)?.label ?? v)
        lines.push(`**${field.label}:** ${labels.join(', ')}`)
      } else {
        if ((val as string).trim()) lines.push(`**${field.label}:** ${val}`)
      }
    })

    const msg = lines.join('\n')
    setDone(true)
    onSubmit(msg)
  }

  if (done) {
    return (
      <div
        className="flex items-center gap-2 mt-2 px-3 py-2 rounded-lg text-[11px] text-cyber-muted"
        style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}
      >
        <Check size={11} className="text-cyber-cyan" />
        Requisitos enviados — Luna está construindo...
      </div>
    )
  }

  return (
    <div
      className="mt-2 rounded-xl overflow-hidden"
      style={{ border: '1px solid rgba(0,212,255,0.15)', background: 'rgba(10,16,28,0.7)' }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex items-center gap-2"
        style={{ background: 'rgba(0,212,255,0.06)', borderBottom: '1px solid rgba(0,212,255,0.1)' }}
      >
        <div
          className="w-5 h-5 rounded flex items-center justify-center"
          style={{ background: 'rgba(0,212,255,0.15)', border: '1px solid rgba(0,212,255,0.3)' }}
        >
          <ChevronRight size={12} className="text-cyber-cyan" />
        </div>
        <h3 className="text-[12px] font-mono font-semibold text-cyber-cyan tracking-wide uppercase">
          {schema.title}
        </h3>
      </div>

      {/* Fields */}
      <div className="px-4 py-3 space-y-4">
        {schema.fields.map((field) => (
          <div key={field.id}>
            <label className="block text-[11px] font-mono text-cyber-muted uppercase tracking-[0.1em] mb-1.5">
              {field.label}
              {field.required && <span className="text-red-400 ml-1">*</span>}
            </label>

            {field.type === 'radio' && (
              <RadioField
                field={field}
                value={values[field.id] as string}
                onChange={(v) => setValue(field.id, v)}
              />
            )}

            {field.type === 'checkboxes' && (
              <CheckboxesField
                field={field}
                values={values[field.id] as string[]}
                onChange={(v) => setValue(field.id, v)}
              />
            )}

            {field.type === 'text' && (
              <input
                type="text"
                value={values[field.id] as string}
                onChange={(e) => setValue(field.id, e.target.value)}
                placeholder={field.placeholder}
                className="w-full bg-transparent rounded-lg px-3 py-2 text-[12px] text-cyber-text font-mono outline-none transition-all"
                style={{
                  border: '1px solid rgba(0,212,255,0.15)',
                  background: 'rgba(0,212,255,0.03)',
                }}
                onFocus={(e) => (e.currentTarget.style.borderColor = 'rgba(0,212,255,0.4)')}
                onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(0,212,255,0.15)')}
              />
            )}

            {field.type === 'textarea' && (
              <textarea
                rows={3}
                value={values[field.id] as string}
                onChange={(e) => setValue(field.id, e.target.value)}
                placeholder={field.placeholder}
                className="w-full bg-transparent rounded-lg px-3 py-2 text-[12px] text-cyber-text font-mono outline-none resize-none transition-all"
                style={{
                  border: '1px solid rgba(0,212,255,0.15)',
                  background: 'rgba(0,212,255,0.03)',
                }}
                onFocus={(e) => (e.currentTarget.style.borderColor = 'rgba(0,212,255,0.4)')}
                onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(0,212,255,0.15)')}
              />
            )}
          </div>
        ))}
      </div>

      {/* Submit */}
      <div
        className="px-4 py-3"
        style={{ borderTop: '1px solid rgba(0,212,255,0.08)' }}
      >
        <button
          type="button"
          onClick={handleSubmit}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-mono text-[12px] font-semibold transition-all duration-150"
          style={{
            background: 'linear-gradient(135deg, rgba(0,212,255,0.15), rgba(124,58,237,0.15))',
            border: '1px solid rgba(0,212,255,0.35)',
            color: '#00d4ff',
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLElement
            el.style.background = 'linear-gradient(135deg, rgba(0,212,255,0.25), rgba(124,58,237,0.25))'
            el.style.borderColor = 'rgba(0,212,255,0.6)'
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLElement
            el.style.background = 'linear-gradient(135deg, rgba(0,212,255,0.15), rgba(124,58,237,0.15))'
            el.style.borderColor = 'rgba(0,212,255,0.35)'
          }}
        >
          <ChevronRight size={13} />
          Confirmar e iniciar
        </button>
      </div>
    </div>
  )
}

// ── Parser ───────────────────────────────────────────────────────────────────

/**
 * Extrai o bloco :::luna-form ... ::: do conteúdo de uma mensagem.
 * Retorna { schema, before, after } ou null se não houver bloco.
 */
export function parseLunaForm(content: string): {
  schema: LunaFormSchema
  before: string
  after: string
} | null {
  const match = content.match(/^([\s\S]*?):::luna-form\n([\s\S]*?)\n:::([\s\S]*)$/)
  if (!match) return null

  try {
    const schema: LunaFormSchema = JSON.parse(match[2])
    return { schema, before: match[1].trim(), after: match[3].trim() }
  } catch {
    return null
  }
}
