import { useState } from 'react'

import { createTicket } from '../api'

const PRIORITY_OPTIONS = ['Low', 'Medium', 'High', 'Critical']
const SETUP_FIELDS = [
  { name: 'server_name', label: 'Server Name', required: true },
  { name: 'server_ip', label: 'Server IP', required: true },
  { name: 'platform', label: 'Platform', required: true },
  { name: 'dut', label: 'DUT', required: true },
  { name: 'pal_server', label: 'PAL Server' },
  { name: 'emp', label: 'EMP' },
  { name: 'console', label: 'Console' },
  { name: 'console_port', label: 'Console Port' },
  { name: 'rps', label: 'RPS' },
  { name: 'rps_port', label: 'RPS Port' },
  { name: 'gateway', label: 'Gateway' },
  { name: 'gateway_port', label: 'Gateway Port' },
  { name: 'ixia', label: 'IXIA' },
  { name: 'ixia_port', label: 'IXIA Port' },
  { name: 'full_model', label: 'Full Model' },
  { name: 'notes', label: 'Notes', wide: true },
]

const INITIAL_FORM = {
  title: '',
  description: '',
  priority: '',
  setup_snapshot: Object.fromEntries(SETUP_FIELDS.map(({ name }) => [name, ''])),
}

function CreateTicketPage() {
  const [form, setForm] = useState(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)
  const [createdTicket, setCreatedTicket] = useState(null)

  function handleFieldChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  function handleSetupChange(event) {
    const { name, value } = event.target
    setForm((current) => ({
      ...current,
      setup_snapshot: { ...current.setup_snapshot, [name]: value },
    }))
  }

  function validateForm() {
    const details = {}
    if (!form.title.trim()) details.title = 'Title is required.'
    if (!form.description.trim()) details.description = 'Description is required.'
    if (!form.priority) details.priority = 'Priority is required.'

    SETUP_FIELDS.filter((field) => field.required).forEach(({ name, label }) => {
      if (!form.setup_snapshot[name].trim()) {
        details[name] = `${label} is required.`
      }
    })

    return Object.keys(details).length > 0 ? details : null
  }

  function formatSubmitError(error) {
    if (!error.details || typeof error.details !== 'object') {
      return error.message
    }

    const details = Object.entries(error.details)
      .flatMap(([field, value]) => {
        if (typeof value === 'object' && value !== null) {
          return Object.entries(value).map(([nestedField, message]) => `${field}.${nestedField}: ${message}`)
        }
        return `${field}: ${value}`
      })

    return details.length > 0 ? `${error.message} ${details.join(' ')}` : error.message
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitError(null)
    setSuccessMessage(null)
    setCreatedTicket(null)

    const validationDetails = validateForm()
    if (validationDetails) {
      setSubmitError(Object.values(validationDetails).join(' '))
      return
    }

    const setupSnapshot = Object.fromEntries(
      Object.entries(form.setup_snapshot).filter(([, value]) => value.trim() !== ''),
    )

    setSubmitting(true)
    try {
      const data = await createTicket({
        title: form.title.trim(),
        description: form.description.trim(),
        priority: form.priority,
        setup_snapshot: setupSnapshot,
      })
      setSuccessMessage('Ticket created successfully.')
      setCreatedTicket(data.ticket)
    } catch (error) {
      setSubmitError(formatSubmitError(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="ticket-form" onSubmit={handleSubmit}>
      <section className="ticket-form-section">
        <h2>Ticket Information</h2>
        <label>
          Title
          <input name="title" value={form.title} onChange={handleFieldChange} maxLength={200} required />
        </label>
        <label>
          Description
          <textarea name="description" value={form.description} onChange={handleFieldChange} rows="5" required />
        </label>
        <label>
          Priority
          <select name="priority" value={form.priority} onChange={handleFieldChange} required>
            <option value="">Select priority</option>
            {PRIORITY_OPTIONS.map((priority) => <option key={priority} value={priority}>{priority}</option>)}
          </select>
        </label>
      </section>

      <section className="ticket-form-section">
        <h2>Setup Information</h2>
        <div className="ticket-form-grid">
          {SETUP_FIELDS.map(({ name, label, required, wide }) => (
            <label className={wide ? 'ticket-form-field-wide' : ''} key={name}>
              {label}{required ? ' *' : ''}
              {name === 'notes' ? (
                <textarea name={name} value={form.setup_snapshot[name]} onChange={handleSetupChange} rows="3" maxLength={4000} required={required} />
              ) : (
                <input name={name} value={form.setup_snapshot[name]} onChange={handleSetupChange} maxLength={name.endsWith('_port') ? 20 : 255} required={required} />
              )}
            </label>
          ))}
        </div>
      </section>

      {submitError && <p className="form-error" role="alert">{submitError}</p>}
      {successMessage && <p className="form-success" role="status">{successMessage}</p>}
      {createdTicket && <p className="form-success-detail">Ticket #{createdTicket.ticket_number} is ready.</p>}
      <button type="submit" disabled={submitting}>{submitting ? 'Creating...' : 'Create Ticket'}</button>
    </form>
  )
}

export default CreateTicketPage