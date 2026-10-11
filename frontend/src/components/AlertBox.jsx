function AlertBox({ message, type = 'status' }) {
  if (!message) {
    return null;
  }

  return <p role={type === 'error' ? 'alert' : 'status'}>{message}</p>;
}

export default AlertBox;
